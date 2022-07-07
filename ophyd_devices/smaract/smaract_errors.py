SMARACT_ERRORS = {
    1: "Syntax Error: The command could not be processed due to a syntactical error.",
    2: "Invalid Command Error: The command given is not known to the system.",
    3: "Overflow Error: This error occurs if a parameter given is too large and therefore cannot be processed.",
    4: "Parse Error: The command could not be processed due to a parse error.",
    5: "Too Few Parameters Error: The specified command requires more parameters in order to be executed.",
    6: "Too Many Parameters Error: There were too many parameters given for the specified command.",
    7: "Invalid Parameter Error: A parameter given exceeds the valid range. Please see the command description for valid ranges of the parameters.",
    8: "Wrong Mode Error: This error is generated if the specified command is not available in the current communication mode. For example, the SRC command is not executable in synchronous mode.",
    129: "No Sensor Present Error: This error occurs if a command was given that requires sensor feedback, but the addressed positioner has none attached.",
    140: "Sensor Disabled Error: This error occurs if a command was given that requires sensor feedback, but the sensor of the addressed positioner is disabled (see SSE command).",
    141: "Command Overridden Error: This error is only generated in the asynchronous communication mode. When the software commands a movement which is then interrupted by the Hand Control Module, an error of this type is generated.",
    142: "End Stop Reached Error: This error is generated in asynchronous mode if the target position of a closed-loop command could not be reached, because a mechanical end stop was detected. After this error the positioner will have a movement status code of 0 (stopped).",
    143: "Wrong Sensor Type Error:  This error occurs if a closed-loop command does not match the sensor type that is currently configured for the addressed channel. For example, issuing a GP command while the targeted channel is configured as rotary will lead to this error.",
    144: "Could Not Find Reference Mark Error: This error is generated in asynchronous mode (see SCM) if the search for a reference mark was aborted.",
    145: "Wrong End Effector Type Error: This error occurs if a command does not match the end effector type that is currently configured for the addressed channel. For example, sending GF while the targeted channel is configured for a gripper will lead to this error.",
    146: "Movement Locked Error: This error occurs if a movement command is issued while the system is in the locked state. ",
    147: "Range Limit Reached Error: If a range limit is defined (SPL or SAL) and the positioner is about to move beyond this limit, then the positioner will stop and report this error (only in asynchronous mode, see SCM). After this error the positioner will have status code of 0 (stopped).",
    148: "Physical Position Unknown Error: A range limit is only allowed to be defined if the positioner “knows” its physical position. If this is not the case, the commands SPL and SAL will return this error code.",
    150: "Command Not Processable Error: This error is generated if a command is sent to a channel when it is in a state where the command cannot be processed. For example, to change the sensor type of a channel the addressed channel must be completely stopped. In this case send a stop command before changing the type.",
    151: "Waiting For Trigger Error: If there is at least one command queued in the command queue then you may only append more commands (if the queue is not full), but you may not issue movement commands for immediate execution. Doing so will generate this error. See section 2.4.5 “Command Queues“.",
    152: "Command Not Triggerable Error: After sending a ATC command you are required to issue a movement command that is to be triggered by the given event source. Commands that cannot be triggered will generate this error.",
    153: "Command Queue Full Error: This error is generated if you attempt to append more commands to the command queue, but the queue cannot hold anymore commands. The queue capacity may be read out with a get channel property command (GCP on p.30).",
    154: "Invalid Component Error: Indicates that a component (e.g. SCP) was selected that does not exist.",
    155: "Invalid Sub Component Error: Indicates that a sub component (e.g. SCP) was selected that does not exist.",
    156: "Invalid Property Error: Indicates that a property (e.g. SCP) was selected that does not exist.",
    157: "Permission Denied Error: This error is generated when you call a functionality which is not unlocked for the system (e.g. Low Vibration Mode).",
}


class SmaractError(Exception):
    pass


class SmaractCommunicationError(SmaractError):
    pass


class SmaractErrorCode(SmaractError):
    def __init__(self, error_code: int, message=""):
        self.error_code = error_code
        self.error_code_message = SMARACT_ERRORS.get(error_code, "UNKNOWN ERROR")
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"{self.error_code} / {self.error_code_message}. {self.message}"
