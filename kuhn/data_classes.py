import pickle
import torch
import numpy as np
from collections import deque
from random import shuffle
import copy

import datatypes as pdt
from cardlib import winner,encode,decode,holdem_hand_rank,holdem_winner

class Action(object):
    def __init__(self,action):
        self.action = action
        
    def item(self):
        return self.action
        
    def readable(self):
        return pdt.Globals.ACTION_DICT[self.action]
    
class Card(object):
    def __init__(self,rank,suit):
        self.rank = rank
        self.suit = suit
        
    def __str__(self):
        printable = f'Rank {self.rank}, Suit {self.suit}' if self.suit else f'Rank {self.rank}'
        return printable
    
class Deck(object):
    def __init__(self,ranks,suits):
        self.ranks = ranks
        self.suits = suits
        self.deck = self.construct_deck()
    
    def construct_deck(self):
        deck = deque(maxlen=52)
        if self.suits is None:
            for rank in self.ranks:
                deck.append(Card(rank,None))
        else:
            for rank in self.ranks:
                for suit in self.suits:
                    deck.append(Card(rank,suit))
        return deck
    
    def deal(self,N):
        cards = []
        for card in range(N):
            cards.append(self.deck.pop())
        return cards

    def initialize_board(self,street):
        num_cards = pdt.Globals.INITIALIZE_BOARD_CARDS[street]
        return self.deal(num_cards)

    def deal_board(self,street):
        num_cards = pdt.Globals.ADDITIONAL_BOARD_CARDS[street]
        return self.deal(num_cards)
    
    def shuffle(self):
        shuffle(self.deck)
        
    def reset(self):
        self.deck = self.construct_deck()
        
    def display(self):
        for card in self.deck:
            print(card)

class Historical_point(object):
    def __init__(self,player,action,betsize):
        self.player = player
        self.action = Action(action)
        self.betsize = betsize
    
    def display(self):
        return (self.player,self.action.readable(),self.betsize)
    
class History(object):
    def __init__(self,initial_state=None):
        if initial_state:
            self.history = initial_state
        else:
            self.history = []
        
    def add(self,player,action,betsize):
        self.history.append(Historical_point(player,action,betsize))
        
    def display(self):
        for step in self.history:
            print(step.display())

    def __getitem__(self,index):
        return self.history[index]

    @property
    def last_betsize(self):
        if len(self.history) > 0:
            return self.history[-1].betsize
        return torch.tensor([0])
            
    @property
    def last_action(self):
        if len(self.history) > 0:
            return self.history[-1].action.item()
        return torch.tensor([5])

    @property
    def penultimate_action(self):
        if len(self.history) > 1:
            return self.history[-2].action.item()
        return torch.tensor([5])

    @property
    def penultimate_betsize(self):
        if len(self.history) > 1:
            return self.history[-2].betsize
        return torch.tensor([0])

    def __len__(self):
        return len(self.history)
    
    def reset(self):
        self.history = []
            
class GameTurn(object):
    def __init__(self,initial_value=0):
        self.initial_value = initial_value
        self.value = initial_value
        
    def increment(self):
        self.value += 1
        
    def reset(self):
        self.value = self.initial_value
    
'''
In the Future we will need to account for side pots
'''
class Pot(object):
    def __init__(self,initial_value:float):
        self.initial_value = initial_value
        self.value = initial_value
        
    def add(self,amount):
        self.value += amount
        
    def update(self,amount):
        self.initial_value = amount
        self.value = amount
        
    def reset(self):
        self.value = self.initial_value
        
class PlayerTurn(object):
    def __init__(self,initial_value:int,max_value=2,min_value=0):
        self.initial_value = initial_value
        self.value = initial_value
        self.min_value = min_value
        self.max_value = max_value
    
    def increment(self):
        self.value = max(((self.value + 1) % self.max_value),self.min_value)
        
    def reset(self):
        self.value = self.initial_value

class Player(object):
    def __init__(self,hand,stack,position,active=True,allin=False,street_total=torch.tensor([0.])):
        self.hand = hand
        self.stack = stack
        self.position = position
        self.active = active
        self.allin = allin
        self.street_total = street_total
        
class Players(object):
    def __init__(self,n_players:int,stacksizes:list,hands:list):
        self.n_players = n_players
        self.stacksizes = stacksizes
        self.initial_positions = pdt.Globals.PLAYERS_POSITIONS_DICT[n_players]
        self.reset(hands)

    def update_hands(self,hands):
        self.hands = hands
        for i,position in enumerate(self.initial_positions):
            self.players[position].hand = [self.hands[i]]

    def update_position_order(self,street):
        self.poker_positions = deque(pdt.Globals.HEADSUP_POSITION_DICT[street],maxlen=9)

    def store_handstrengths(self,board):
        board_cards = [[card.rank,card.suit] for card in board]
        en_board = [encode(c) for c in board_cards]
        for player in range(self.n_players):
            position = self.initial_positions[player]
            hand_cards = [[card.rank,card.suit] for card in self.players[position].hand]
            en_hand = [encode(c) for c in hand_cards]
            self.player_handstrength[position] = holdem_hand_rank(en_hand,en_board)
        
    def reset(self,hands:list):
        self.hands = hands
        self.poker_positions = deque(self.initial_positions,maxlen=9)
        self.players = {position:Player(hands[i],self.stacksizes[i].clone(),position,street_total=torch.tensor([0.])) for i,position in enumerate(self.poker_positions)}
        self.player_hand = {position:hands[i][0].rank for i,position in enumerate(self.poker_positions)}
        self.game_states = {position:[] for position in self.poker_positions}
        self.observations = {position:[] for position in self.poker_positions}
        self.actions = {position:[] for position in self.poker_positions}
        self.action_prob = {position:[] for position in self.poker_positions}
        self.action_probs = {position:[] for position in self.poker_positions}
        self.values = {position:[] for position in self.poker_positions}
        self.betsize_values = {position:[] for position in self.poker_positions}
        self.rewards = {position:[] for position in self.poker_positions}
        self.betsizes = {position:[] for position in self.poker_positions}
        self.betsize_prob = {position:[] for position in self.poker_positions}
        self.betsize_probs = {position:[] for position in self.poker_positions}
        self.action_masks = {position:[] for position in self.poker_positions}
        self.betsize_masks = {position:[] for position in self.poker_positions}
        self.player_turns = {position:0 for position in self.poker_positions}
        self.player_handstrength = {position:0 for position in self.poker_positions}
        self.historical_game_states = {position:[] for position in self.poker_positions}
        
    def store_states(self,state:torch.Tensor,obs:torch.Tensor,player=None):
        position = self.current_player if player == None else player
        self.observations[position].append(copy.deepcopy(obs))
        self.game_states[position].append(copy.deepcopy(state))

    def store_history(self,state:torch.Tensor,player=None):
        position = self.current_player if player == None else player
        self.historical_game_states[position].append(copy.deepcopy(state))

    def store_masks(self,action_mask:torch.Tensor,betsize_mask:torch.Tensor):
        self.action_masks[self.current_player].append(action_mask)
        self.betsize_masks[self.current_player].append(betsize_mask)
        
    def store_actor_outputs(self,actor_outputs):
        self.store_actions(actor_outputs['action'],actor_outputs['action_prob'],actor_outputs['action_probs'])
        if 'betsize' in actor_outputs:
            if 'betsize_prob' in actor_outputs:
                self.store_betsizes(actor_outputs['betsize'],actor_outputs['betsize_prob'],actor_outputs['betsize_probs'])
            else:
                self.betsizes[self.current_player].append(actor_outputs['betsize'])
                
    def store_actions(self,action:int,action_prob:torch.Tensor,action_probs:torch.Tensor):
        self.actions[self.current_player].append(action)
        self.action_prob[self.current_player].append(action_prob)
        self.action_probs[self.current_player].append(action_probs)

    def store_betsizes(self,betsize:int,betsize_prob:torch.Tensor,betsize_probs:torch.Tensor):
        self.betsizes[self.current_player].append(betsize)
        self.betsize_prob[self.current_player].append(betsize_prob)
        self.betsize_probs[self.current_player].append(betsize_probs)

    def store_values(self,critic_outputs:dict):
        self.values[self.current_player].append(critic_outputs['value'])
        if len(critic_outputs.keys()) == 2:
            self.betsize_values[self.current_player].append(critic_outputs['betsize'])
        
    def store_rewards(self,position:str,reward:float):
        N = self.player_turns[position]
        torch_rewards = torch.Tensor(N).fill_(reward)#.view(N,1)
        self.rewards[position].append(torch_rewards)
        
    def update_stack(self,amount:torch.Tensor,player=None):
        """
        Updates player stack,street_total,active after putting money into the pot.
        amount typically is a negative number
        """
        if amount.dim() > 0:
            amount = amount.squeeze(0)
        if player == None:
            self.players[self.current_player].stack += amount
            self.players[self.current_player].street_total -= amount
            if self.players[self.current_player].stack == 0:
                self.players[self.current_player].allin = True
        else:
            self.players[player].stack += amount
            self.players[player].street_total -= amount
            if self.players[player].stack == 0:
                self.players[player].allin = True

    def reset_street_totals(self):
        for player in self.players.values():
            player.street_total = torch.tensor([0.])
    
    def increment(self):
        self.player_turns[self.current_player] += 1
        self.poker_positions.rotate(1)
        
    def gen_rewards(self):
        for i,initial_stacksize in enumerate(self.stacksizes):
            position = pdt.Globals.PLAYERS_POSITIONS_DICT[self.n_players][i]
            player = self.players[position]
            self.store_rewards(position,player.stack - initial_stacksize)
    
    def get_player(self,position):
        return self.players[position]
    
    def get_hands(self):
        '''
        Later will take an argument for active players
        '''
        hands = []
        for player in range(self.n_players):
            position = self.initial_positions[player]
            hands.append(self.players[position].hand)
        return hands

    def get_allins(self):
        """
        Only for HU.
        Technically should be if all active players are allin.
        """
        return [self.players[position].allin for position in self.initial_positions]
    
    def get_inputs(self):
        ml_inputs = {}
        del_positions = set()
        for position in self.initial_positions:
            if len(self.actions[position]):
                ml_inputs[position] = {
                    'hand':self.player_hand[position],
                    'hand_strength':self.player_handstrength[position],
                    'historical_game_states':self.historical_game_states[position],
                    'game_states':self.game_states[position],
                    'observations':self.observations[position],
                    'actions':self.actions[position],
                    'action_prob':self.action_prob[position],
                    'action_probs':self.action_probs[position],
                    'betsizes':self.betsizes[position],
                    'betsize_prob':self.betsize_prob[position],
                    'betsize_probs':self.betsize_probs[position],
                    'action_masks':self.action_masks[position],
                    'betsize_masks':self.betsize_masks[position],
                    'rewards':self.rewards[position],
                    'values':self.values[position]
                }
                assert(self.rewards[position][0].size(0) == len(self.actions[position]))
            else:
                if position not in del_positions:
                    del_positions.add(position)
        for position in del_positions:
            if position in ml_inputs:
                del ml_inputs[position]
        return ml_inputs
    
    def get_stats(self):
        stats = {}
        for position in self.initial_positions:
            stats[position] = {
                'hand':self.players[position].hand,
                'position':position,
                'stack':self.players[position].stack,
            }
        return stats
        
    @property
    def to_showdown(self):
        """
        Only for HU.
        Technically should be if all active players are allin.
        """
        return False not in self.get_allins()

    @property
    def current_hand(self):
        return self.players[self.current_player].hand
    
    @property
    def current_stack(self):
        return self.players[self.current_player].stack

    @property
    def current_player(self):
        return self.poker_positions[0]

    @property
    def current_street_total(self):
        return self.players[self.current_player].street_total
    
    @property
    def previous_player(self):
        return self.poker_positions[-1]

    @property
    def previous_stack(self):
        return self.players[self.previous_player].stack

    @property
    def previous_hand(self):
        return self.players[self.previous_player].hand
    
    @property
    def previous_street_total(self):
        return self.players[self.previous_player].street_total

class Rules(object):
    def __init__(self,params):
        self.load_rules(params)

    def return_mask(self,state):
        if state.dim() > 2:
            return self.mask_dict[state[-1,-1,self.db_mapping['state']['previous_action']].long().item()]
        else: 
            return self.mask_dict[state[-1,self.db_mapping['state']['previous_action']].long().item()]
        
    def load_rules(self,params):
        if 'network_output' in params:
            self.network_output = params['network_output']
        self.bettype = params['bettype']
        self.blinds = params['blinds']
        self.minbet = self.blinds['BB']
        self.betsize = params['betsize']
        self.betsizes = params['betsizes']
        self.num_betsizes = len(self.betsizes)
        self.unopened_action = params['unopened_action']
        self.action_dict = params['action_dict']
        self.mask_dict = params['mask_dict']
        self.bets_per_street = params['bets_per_street']
        self.db_mapping = params['mapping']
        self.action_space = len(self.action_dict.keys())
        self.over = self.two_actions if self.bets_per_street == 1 else self.multiple_actions

    def multiple_actions(self,env):
        done = False
        if env.history.last_action == pdt.Globals.REVERSE_ACTION_ORDER[pdt.Actions.FOLD]:
            done = True
        elif env.street == 0:
            if (env.history.penultimate_action == pdt.Globals.REVERSE_ACTION_ORDER[pdt.Actions.CALL] and env.history.last_action == pdt.Globals.REVERSE_ACTION_ORDER[pdt.Actions.CHECK]) or (env.history.last_action == pdt.Globals.REVERSE_ACTION_ORDER[pdt.Actions.CALL] and env.action_records[env.street][pdt.Globals.REVERSE_ACTION_ORDER[pdt.Actions.RAISE]] > 0):
                done = True
        elif (env.history.last_action == pdt.Globals.REVERSE_ACTION_ORDER[pdt.Actions.CHECK] and env.history.penultimate_action == pdt.Globals.REVERSE_ACTION_ORDER[pdt.Actions.CHECK]) or env.history.last_action == pdt.Globals.REVERSE_ACTION_ORDER[pdt.Actions.CALL]:
            done = True
        return done
        
    def two_actions(self,env):
        done = False
        if env.history.last_action == pdt.Globals.REVERSE_ACTION_ORDER[pdt.Actions.FOLD] or env.history.last_action == pdt.Globals.REVERSE_ACTION_ORDER[pdt.Actions.CALL] or env.history.last_action == pdt.Globals.REVERSE_ACTION_ORDER[pdt.Actions.CHECK]:
            done = True
        return done
    
def eval_kuhn(cards):
    hand1,hand2 = cards
    ranks = [card.rank for card in hand1+hand2]
    return np.argmax(ranks)

class Evaluator(object):
    def __init__(self,game):
        self.game = game
        self.evaluate = eval_kuhn
        
    def __call__(self,cards):
        return self.evaluate(cards)