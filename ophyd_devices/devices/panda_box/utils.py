PANDA_AVAIL_PCAP_BLOCKS = [
    "INENC1.VAL",
    "INENC2.VAL",
    "INENC3.VAL",
    "INENC4.VAL",
    "PCAP.TS_START",
    "PCAP.TS_END",
    "PCAP.TS_TRIG",
    "PCAP.GATE_DURATION",
    "PCAP.BITS0",
    "PCAP.BITS1",
    "PCAP.BITS2",
    "PCAP.BITS3",
    "CALC1.OUT",
    "CALC2.OUT",
    "COUNTER1.OUT",
    "COUNTER2.OUT",
    "COUNTER3.OUT",
    "COUNTER4.OUT",
    "COUNTER5.OUT",
    "COUNTER6.OUT",
    "COUNTER7.OUT",
    "COUNTER8.OUT",
    "FILTER1.OUT",
    "FILTER2.OUT",
    "PGEN1.OUT",
    "PGEN2.OUT",
    "FMC_IN.VAL1",
    "FMC_IN.VAL2",
    "FMC_IN.VAL3",
    "FMC_IN.VAL4",
    "FMC_IN.VAL5",
    "FMC_IN.VAL6",
    "FMC_IN.VAL7",
    "FMC_IN.VAL8",
    "SFP3_SYNC_IN.POS1",
    "SFP3_SYNC_IN.POS2",
    "SFP3_SYNC_IN.POS3",
    "SFP3_SYNC_IN.POS4",
]

PANDA_AVAIL_PCAP_CAPTURE_FIELDS = ["Value", "Diff", "Sum", "Mean", "Min", "Max"]


def get_pcap_capture_fields():
    out = []
    for block in PANDA_AVAIL_PCAP_BLOCKS:
        for field in PANDA_AVAIL_PCAP_CAPTURE_FIELDS:
            out.append(f"{block}.{field}")
    return out
