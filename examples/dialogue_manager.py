import os
import json
import random
import string
import yaml
from collections import deque
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from triggering.fuzzy import FuzzySystem

class RotatingQueue:
    def __init__(self, iterable):
        self.data = deque(iterable)
    
    def query(self):
        element = self.data.popleft()
        self.data.append(element)
        return element

    def __str__(self):
        return json.dumps(list(self.data))
    
    def __repr__(self):
        return str(self)[:15]+'...'


class GroupCache:
    def __init__(self, talk_moves: List[Dict], followups: List[Dict] = None, repetition_window: int = 3):
        self.talk_moves = {}
        for item in talk_moves:
            variations = item['value']
            if isinstance(variations, str):
                variations = [variations]
            self.talk_moves[item['id']] = RotatingQueue(variations)
            
        self.followups = {}
        if followups:
            for item in followups:
                variations = item['value']
                if isinstance(variations, str):
                    variations = [variations]
                self.followups[item['id']] = RotatingQueue(variations)
        else:
            self.followups = None
            
        self.tm_freqs = {tm: 0 for tm in self.talk_moves}
        self.last_tms = deque(maxlen=repetition_window)
        self.last_tm_addressed_user = None
        self.words_addressed_user = 0
        self.followup_delivered = True 
        self.last_smalltalk = deque(maxlen=5)
        self.msgs_since_last_tm = 0
        self.time_last_tm = datetime.fromtimestamp(0, tz=timezone.utc)

    def update(self, talk_move, timestamp: datetime, followup=None, addressed_user=None, trigger_only_once=None, username=None, text=None):
        if talk_move in self.talk_moves:
            if trigger_only_once is None or \
               (talk_move not in trigger_only_once) or \
               (talk_move in trigger_only_once and self.tm_freqs[talk_move] == 0):
                self.tm_freqs[talk_move] += 1
                self.last_tms.append(talk_move)
                self.last_tm_addressed_user = addressed_user
                self.words_addressed_user = 0
                self.followup_delivered = False
                self.msgs_since_last_tm = 0

            self.time_last_tm = timestamp
        else:
            self.msgs_since_last_tm += 1
            if username is not None and username == self.last_tm_addressed_user and text:
                self.words_addressed_user += len(text.split())
                
        if self.followups and followup in self.followups:
            self.followup_delivered = True
            self.msgs_since_last_tm = 0  


class AgentManager:
    AGENT_NAME = "Clair"

    def __init__(self, modes_dir: str = "triggering/modes"):
        self.blacklist_groups = {}
        self.blacklist_users = set()
        self.group_cache = {}
        self.interventions = {} 
        self.fuzzy_systems = {}
        
        # In a real app, this would load unified yaml configs. 
        # For this example, we'll keep the legacy folder structure logic to show how it wraps FuzzySystem
        if os.path.exists(modes_dir):
            modes = [f for f in os.listdir(modes_dir) if not f.startswith('.') and os.path.isdir(os.path.join(modes_dir, f))]
            for mode in modes:
                self.interventions[mode] = {}
                # Here we assume there's a consolidated clair_apt_base.yml equivalent
                unified_config = f"examples/clair_{mode.replace('-', '_')}.yml"
                if os.path.exists(unified_config):
                    self.fuzzy_systems[mode] = FuzzySystem(config_path=unified_config)
                
                for item in ['config', 'talk_moves', 'small_talk', 'followups', 'what_ifs']:
                    file_path = os.path.join(modes_dir, mode, f'{item}.yml')
                    if os.path.exists(file_path):
                        with open(file_path, 'r', encoding='utf-8') as f:
                            self.interventions[mode][item] = yaml.safe_load(f)

    def generate_intervention(self, 
                              learning_space: str,
                              group: str, 
                              username: str, 
                              timestamp: datetime,
                              text: str, 
                              intent: str,
                              last_users: List[str],
                              tacc: Dict[str, float],
                              content_statement: str, 
                              dialogue_state: Dict[str, float], 
                              mode: str, 
                              language: str, 
                              verbose=False) -> Dict[str, Optional[str]]:
        if mode not in self.interventions:
            raise ValueError(f"Mode {mode} not supported.")
            
        talk_move, agent_response = None, None
        addressed_user = None
        followup = None
        trigger_only_once = None

        if language not in self.interventions[mode].get('talk_moves', {}):
            language = 'EN'

        is_not_group = last_users is not None and len(last_users) < 2
        is_from_agent = username == self.AGENT_NAME
        is_user_blacklisted = username in self.blacklist_users
        is_group_blacklisted = group in self.blacklist_groups.get(learning_space, set())
        
        if is_not_group or is_from_agent or is_user_blacklisted or is_group_blacklisted:
            return {'selected_move': None, 'text': None}        
        
        if group not in self.group_cache:
            followups = self.interventions[mode].get('followups', {}).get(language.upper()[:2])
            self.group_cache[group] = GroupCache(
                talk_moves=self.interventions[mode]['talk_moves'][language], 
                followups=followups,
                repetition_window=self.interventions[mode]['config']['repetition_window']
            )
            agent_response = self.interventions[mode]['small_talk'][language]['greetings']

        elif text and intent and ('clair' in text.lower()[:10]):
            agent_response = self.interventions[mode]['small_talk'][language].get(intent, None)
            if agent_response is not None:
                self.group_cache[group].last_smalltalk.append(intent)
                if self.group_cache[group].last_smalltalk.count(intent) >= 3:
                    agent_response = None

        elif text and self.is_for_followup(group, username, timestamp, text, mode) \
             and not self.group_cache[group].followup_delivered:
            last_talk_move = self.group_cache[group].last_tms[-1]
            followups_q = self.group_cache[group].followups.get(last_talk_move, None)
            if followups_q is not None:
                agent_response = followups_q.query()
                followup = last_talk_move
                
        else:
            text_len = len(text.split(' ')) if text else 0
            config = self.interventions[mode]['config']
            is_too_short = username is not None and text_len < config['min_words_in_message']
            is_too_long = username is not None and text_len > config['max_words_in_message']
            is_silence_window = self.group_cache[group].msgs_since_last_tm < config['silence_window']
            ends_with_special_char = text and not (text[-1].isalnum() or text[-1] in string.punctuation)
        
            if not is_too_short and not is_too_long and not is_silence_window and not ends_with_special_char:
                if mode in self.fuzzy_systems:
                    fuzzy_outputs = self.fuzzy_systems[mode].compute(dialogue_state)
                    talk_move = self.select_talk_move(group, fuzzy_outputs, mode)
                    
                    if talk_move is not None:
                        trigger_only_once = config.get('trigger_output_only_once', None)
                        if trigger_only_once and (talk_move in trigger_only_once) and (self.group_cache[group].tm_freqs[talk_move] > 0):
                            pass 
                        else:
                            agent_response = self.group_cache[group].talk_moves[talk_move].query()

        if agent_response is not None:
            speaker = last_users[0]
            if len(last_users) > 1 and isinstance(tacc, dict) and tacc:
                candidates = [k for k, v in tacc.items() if k != speaker]
                if candidates:
                    discussant = min(candidates, key=lambda k: tacc[k])
                else:
                    discussant = speaker
            else:
                discussant = speaker
                
            if agent_response.startswith('<speaker>'):
                addressed_user = speaker
            elif agent_response.startswith('<discussant>'):
                addressed_user = discussant
                
            def clean_name(name):
                name = ' '.join(word for word in name.split() if not word.isdigit()).strip()
                return '-'.join(substring.capitalize() for substring in name.split('-'))

            speaker = clean_name(speaker)
            discussant = clean_name(discussant)
            
            if '<speaker>' in agent_response:
                agent_response = agent_response.replace('<speaker>', speaker)
            if '<discussant>' in agent_response:
                agent_response = agent_response.replace('<discussant>', discussant)
            if '<what_if>' in agent_response:
                what_if_text = self.interventions[mode]['what_ifs'][language].get(content_statement, "")
                agent_response = agent_response.replace('<what_if>', what_if_text) 

        self.group_cache[group].update(talk_move, timestamp, followup, addressed_user, trigger_only_once, username, text)

        return {'selected_move': talk_move, 'text': agent_response}
    
    def is_for_followup(self, group: str, username: str, timestamp: datetime, text: str, mode: str) -> bool:
        if not self.interventions[mode].get('followups'):
            return False
            
        time_since_last_tm = timestamp - self.group_cache[group].time_last_tm
        is_within_followup_time_window = 1 < time_since_last_tm.total_seconds() < 120
        is_from_addressed_user = username == self.group_cache[group].last_tm_addressed_user
        is_not_question = '?' not in text
        
        n_words = len(text.split(' '))
        is_not_too_short = n_words > self.interventions[mode]['config']['min_words_in_message']
        
        words_addressed_user = self.group_cache[group].words_addressed_user + n_words if is_from_addressed_user else 0
        is_more_than_few_words = words_addressed_user > 5 
        
        return (is_within_followup_time_window and is_from_addressed_user and 
                is_not_question and is_not_too_short and is_more_than_few_words)

    def select_talk_move(self, group: str, fuzzy_outputs: Dict[str, float], mode: str) -> Optional[str]:
        selected = None
        candidates = [tm for tm in fuzzy_outputs if fuzzy_outputs[tm] > 0]
        if not candidates:
            return None
            
        max_val = max(fuzzy_outputs.values())
        threshold = self.interventions[mode]['config']['sensitivity_threshold']
        
        if max_val >= threshold:
            max_candidates = [k for k, v in fuzzy_outputs.items() if v == max_val and k not in self.group_cache[group].last_tms]
            if not max_candidates:
                filtered_outputs = {k: v for k, v in fuzzy_outputs.items() if v < max_val and k not in self.group_cache[group].last_tms}
                if filtered_outputs:
                    max_val = max(filtered_outputs.values())
                    max_candidates = [k for k, v in filtered_outputs.items() if v == max_val and v > 0.5]
                    
            if max_candidates:
                min_freq = min(self.group_cache[group].tm_freqs[k] for k in max_candidates)
                selected_cands = [tm for tm in max_candidates if self.group_cache[group].tm_freqs[tm] == min_freq]
                selected = random.choice(selected_cands)
                
        return selected
