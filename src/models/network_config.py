import kuhn.datatypes as pdt
import poker.datatypes as hdt
from models.networks import *

class CriticType:
    Q='q'
    REG='reg'

class NetworkConfig(object):
    EnvModels = {
            pdt.GameTypes.KUHN : {
                'actor':Baseline,
                'critic':{
                    CriticType.Q : BaselineCritic,
                    CriticType.REG : BaselineKuhnCritic
                },
                'combined': FlatAC},
            pdt.GameTypes.COMPLEXKUHN : {
                'actor':Baseline,
                'critic':{
                    CriticType.Q : BaselineCritic,
                    CriticType.REG : BaselineKuhnCritic
                },
                'combined': FlatAC},
            pdt.GameTypes.BETSIZEKUHN : {
                'actor':FlatBetsizeActor,
                'critic':{
                    CriticType.Q : FlatBetsizeCritic,
                    CriticType.REG : BaselineKuhnCritic
                },
                'combined': FlatAC
                },
            pdt.GameTypes.HISTORICALKUHN : {
                'actor':FlatHistoricalActor,
                'critic':{
                    CriticType.Q : FlatHistoricalCritic,
                    CriticType.REG : BaselineKuhnCritic
                },
                'combined': FlatAC
                },
            hdt.GameTypes.HOLDEM : {
                'actor':HoldemBaseline,
                'critic':{
                    CriticType.Q : HoldemQCritic,
                    CriticType.REG : HoldemBaselineCritic
                },
                'combined': FlatAC},
            hdt.GameTypes.OMAHAHI : {
                'actor':HoldemBaseline,
                'critic':{
                    CriticType.Q : HoldemQCritic,
                    CriticType.REG : HoldemBaselineCritic
                },
                'combined': FlatAC
            },
        }