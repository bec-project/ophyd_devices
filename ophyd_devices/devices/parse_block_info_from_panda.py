
def main():
    from ophyd_devices.devices.panda_box import PandaController
    from ophyd_devices.devices.panda_blocks import PANDA_TYPES
    from ophyd_devices.devices.panda_fields import PANDA_FIELDS

    from pandablocks.commands import Raw
    controller = PandaController(name="redpanda", socket_host="x02da-panda-2.psi.ch")
    # Get info about fields for all blocks
    block_info = {}
    # loop over name of all blocks
    for name in PANDA_TYPES:
        block_info[name] = {}
        field_info = controller.send_command(Raw(f"{name}.*?"))
        for field in sorted(field_info):
            if not field.strip("."):
                continue
            field_name = field.split(" ")[0].strip("!")
            field_type = field.split(" ")[2:]
            block_info[name][field_name] = {"type" : field_type}

    print(block_info)
    import yaml
    import os
    cur_dir  = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(cur_dir, "block_info.yaml")
    with open(output_file, "w") as file:
        yaml.dump(block_info, file, default_flow_style=False)

    

if __name__ == "__main__":
    main()