
import time
import torch.multiprocessing as mp
import torch

from train import train
from train_parallel import train_shared_model
from poker.config import Config
import poker.datatypes as pdt
from poker.multistreet_env import MSPoker
from db import MongoDB
from models.network_config import NetworkConfig,CriticType
from models.networks import FlatHistoricalActor,FlatHistoricalCritic
from agents.agent import return_agent
from utils.utils import unpack_shared_dict

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=
        """
        Run RL experiments with varying levels of complexity in poker.\n\n
        Modify the traiing params via the config file.\n
        """)

    parser.add_argument('--agent',
                        default=pdt.AgentTypes.SPLIT,
                        metavar=f"[{pdt.AgentTypes.SPLIT},{pdt.AgentTypes.SINGLE},{pdt.AgentTypes.SPLIT_OBS}]",
                        type=str,
                        help='Which type of actor critic to train with.\
                        Split: Separate networks for actor and critic, both train on state\
                        Single: 1 Network for actor and critic. trains on state\
                        Split_obs: Separate networks for actor and critic, actor trains on state, critic trains on obs')
    parser.add_argument('--game',
                        default=pdt.GameTypes.OMAHAHI,
                        type=str,
                        metavar=f"[{pdt.GameTypes.HOLDEM},{pdt.GameTypes.OMAHAHI}]",
                        help='Picks which type of poker env to train in')
    parser.add_argument('--no-clean',
                        default=True,
                        dest='clean',
                        action='store_false',
                        help='Cleans database')
    parser.add_argument('--no-store',
                        default=True,
                        dest='store',
                        action='store_false',
                        help='Stores training data in database')
    parser.add_argument('-e','--epochs',
                        default=1000,
                        type=int,
                        help='Number of training epochs')
    parser.add_argument('--betsize',
                        default=2,
                        type=int,
                        metavar="[1-5 or 11]",
                        help='Number of betsizes the agent can make')
    parser.add_argument('--output',
                        default='flat',
                        dest='network_output',
                        type=str,
                        metavar=f"[{pdt.OutputTypes.FLAT},{pdt.OutputTypes.TIERED}]",
                        help='Network output types. Controls whether betsize is combined with actions or not')
    parser.add_argument('--maxlen',
                        default=20,
                        dest='seq_maxlen',
                        type=int,
                        help='Max length of the history to feed into the agent.')
    parser.add_argument('--parallel',
                        default=False,
                        action='store_true',
                        help='Train in parallel')

    args = parser.parse_args()

    print("Number of processors: ", mp.cpu_count())
    print(f'args {args}')
    tic = time.time()
    
    assert args.agent in f"[{pdt.AgentTypes.SPLIT_OBS},{pdt.AgentTypes.SPLIT_OBS},{pdt.AgentTypes.SPLIT_OBS}]",'Invalid agent selection'
    assert args.network_output in f"[{pdt.OutputTypes.FLAT},{pdt.OutputTypes.TIERED}]",'Invalid output selection'
    assert args.game in f"[{pdt.GameTypes.HOLDEM},{pdt.GameTypes.OMAHAHI}]",'Invalid game selection'

    game_object = pdt.Globals.GameTypeDict[args.game]
    config = Config()
    config.agent = args.agent
    env_params = {'game':args.game}
    env_params['state_params'] = game_object.state_params
    env_params['rule_params'] = game_object.rule_params
    env_params['rule_params']['network_output'] = args.network_output
    env_params['rule_params']['betsizes'] = pdt.Globals.BETSIZE_DICT[args.betsize]
    env_params['starting_street'] = game_object.starting_street
    env_params['maxlen'] = config.maxlen
    agent_params = config.agent_params

    env_networks = NetworkConfig.EnvModels[args.game]
    agent_params['network'] = env_networks['actor']
    agent_params['actor_network'] = env_networks['actor']
    agent_params['critic_network'] = env_networks['critic']['q']
    agent_params['combined_network'] = env_networks['combined']
    agent_params['mapping'] = env_params['rule_params']['mapping']
    agent_params['max_reward'] = env_params['state_params']['stacksize'] + env_params['state_params']['pot']
    agent_params['min_reward'] = env_params['state_params']['stacksize']
    agent_params['epochs'] = int(args.epochs)
    agent_params['network_output'] = args.network_output
    agent_params['maxlen'] = config.maxlen
    agent_params['game'] = args.game

    print(f'Training the following networks {agent_params["critic_network"].__name__},{agent_params["actor_network"].__name__}')

    training_data = {}
    for position in pdt.Globals.PLAYERS_POSITIONS_DICT[env_params['state_params']['n_players']]:
        training_data[position] = []
    training_data['action_records'] = []
        
    training_params = config.training_params
    training_params['epochs'] = int(args.epochs)
    training_params['training_data'] = training_data
    training_params['agent_name'] = f'{args.game}_baseline'
    training_params['agent_type'] = args.agent

    env = MSPoker(env_params)

    nS = env.state_space
    nO = env.observation_space
    nA = env.action_space
    nB = env.betsize_space
    nC = nA - 2 + nB
    print(f'Environment: State Space {nS}, Obs Space {nO}, Action Space {nA}, Betsize Space {nB}, Flat Action Space {nC}')

    if args.parallel == True:
        mp.set_start_method('spawn')
        # offline training TODO
        # manager = mp.Manager()
        # return_dict = manager.dict()
        # online training
        mongo = MongoDB()
        mongo.clean_db()
        mongo.close()
        seed = 123
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        actor = agent_params['actor_network'](seed,nS,nA,nB,agent_params)
        critic = agent_params['critic_network'](seed,nS,nA,nB,agent_params)
        del env
        actor.share_memory()#.to(device)
        critic.share_memory()#.to(device)
        processes = []
        num_processes = mp.cpu_count()
        if args.clean:
            print('Cleaning db')
            mongo = MongoDB()
            mongo.clean_db()
            del mongo
        for i in range(num_processes): # No. of processes
            p = mp.Process(target=train_shared_model, args=(agent_params,env_params,training_params,i,actor,critic))
            p.start()
            processes.append(p)
        for p in processes: 
            p.join()
        torch.save(actor.state_dict(), '/Users/morgan/Code/PokerAI/src/checkpoints/RL/Holdem' + '_actor')
        torch.save(critic.state_dict(), '/Users/morgan/Code/PokerAI/src/checkpoints/RL/Holdem' + '_critic')
    else:
        seed = 154
        agent = return_agent(training_params['agent_type'],nS,nO,nA,nB,seed,agent_params)
        action_data = train(env,agent,training_params)
        # print(action_data)
        if args.store:
            print('\nStoring training data')
            mongo = MongoDB()
            if args.clean:
                print('Cleaning db')
                mongo.clean_db()
            mongo.store_data(action_data,env.db_mapping,training_params['training_round'],env.game)

    toc = time.time()
    print(f'\nExecution took {(toc-tic)/60} minutes')