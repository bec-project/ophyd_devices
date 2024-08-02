from abc import ABC


class PandaBlock(ABC):

    def __init__(self, name:str, block_type):
        self.block_type = block_type
        self.name = name

class BITSBlock(PandaBlock):
    pass

class CALCBlock(PandaBlock):
    pass

PANDA_TYPES = {
    "BITS": BITSBlock,
    "CALC1": CALCBlock,
    "CALC2": CALCBlock,
    "CLOCK1": PandaBlock,
    "CLOCK2": PandaBlock,
    "COUNTER1": PandaBlock,
    "COUNTER2": PandaBlock,
    "COUNTER3": PandaBlock,
    "COUNTER4": PandaBlock,
    "COUNTER5": PandaBlock,
    "COUNTER6": PandaBlock,
    "COUNTER7": PandaBlock,
    "COUNTER8": PandaBlock,
    "DIV1": PandaBlock,
    "DIV2": PandaBlock,
    "FILTER1": PandaBlock,
    "FILTER2": PandaBlock,
    "FMC_IN": PandaBlock,
    "FMC_OUT": PandaBlock,
    "INENC1": PandaBlock,
    "INENC2": PandaBlock,
    "INENC3": PandaBlock,
    "INENC4": PandaBlock,
    "LUT1": PandaBlock,
    "LUT2": PandaBlock,
    "LUT3": PandaBlock,
    "LUT4": PandaBlock,
    "LUT5": PandaBlock,
    "LUT6": PandaBlock,
    "LUT8": PandaBlock,
    "LVDSIN1": PandaBlock,
    "LVDSIN2": PandaBlock,
    "LVDSOUT1": PandaBlock,
    "LVDSOUT2": PandaBlock,
    "OUTENC1": PandaBlock,
    "OUTENC2": PandaBlock,
    "OUTENC3": PandaBlock,
    "OUTENC4": PandaBlock,
    "PCAP": PandaBlock,
    "PCOMP1": PandaBlock,
    "PCOMP2": PandaBlock,
    "PGEN1": PandaBlock,
    "PGEN2": PandaBlock,
    "PULSE1": PandaBlock,
    "PULSE2": PandaBlock,
    "PULSE3": PandaBlock,
    "PULSE4": PandaBlock,
    "SEQ1": PandaBlock,
    "SEQ2": PandaBlock,
    "SFP3_SYNC_IN": PandaBlock,
    "SFP3_SYNC_OUT": PandaBlock,
    "SRGATE1": PandaBlock,
    "SRGATE2": PandaBlock,
    "SRGATE3": PandaBlock,
    "SRGATE4": PandaBlock,
    "SYSTEM": PandaBlock,
    "TTLIN1": PandaBlock,
    "TTLIN2": PandaBlock,
    "TTLIN3": PandaBlock,
    "TTLIN4": PandaBlock,
    "TTLIN5": PandaBlock,
    "TTLIN6": PandaBlock,
    "TTLOUT1": PandaBlock,
    "TTLOUT2": PandaBlock,
    "TTLOUT3": PandaBlock,
    "TTLOUT4": PandaBlock,
    "TTLOUT5": PandaBlock,
    "TTLOUT6": PandaBlock,
    "TTLOUT7": PandaBlock,
    "TTLOUT8": PandaBlock,
    "TTLOUT9": PandaBlock,
    "TTLOUT10": PandaBlock,
}

