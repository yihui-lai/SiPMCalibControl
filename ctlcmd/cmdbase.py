import cmod.gcoder as gcoder
import cmod.board as board
import cmod.logger as logger
import cmod.trigger as trigger
import cmod.visual as visual
import cmod.readout as readout
import cmod.sshfiler as sshfiler
import cmd
import sys
import os
import argparse
import readline
import glob


class controlsession(object):
  """
  Object for storing session information. Will include storage and read-in
  function
  """

  def __init__(self):
    ## Stuff for illumination alignment
    self.lumi_halign_x = {}
    self.lumi_halign_y = {}
    self.lumi_halign_xunc = {}
    self.lumi_halign_yunc = {}

    ## Stuff of visual alignment
    self.vis_halign_x = {}
    self.vis_halign_y = {}

    ## Stuff for visual alignment
    self.camT = {}


class controlterm(cmd.Cmd):
  """
  Control term is the class for parsing commands and passing the arguments
  to C functions for gantry and readout control.
  It also handles the command as classes to allow for easier interfacing
  """

  intro = """
    SiPM Calibration Gantry Control System
    Type help or ? to list commands.\n"""
  prompt = 'SiPMCalib> '

  def __init__(self, cmdlist):
    cmd.Cmd.__init__(self)

    ## Creating command instances and attaching to associated functions
    for com in cmdlist:
      comname = com.__name__.lower()
      dofunc = "do_" + comname
      helpfunc = "help_" + comname
      compfunc = "complete_" + comname
      self.__setattr__(comname, com(self))
      self.__setattr__(dofunc, self.__getattribute__(comname).do)
      self.__setattr__(helpfunc, self.__getattribute__(comname).callhelp)
      self.__setattr__(compfunc, self.__getattribute__(comname).complete)
      self.__getattribute__(comname).cmd = self

    # Removing hyphen and slash as completer delimiter, as it messes with
    # command auto completion
    readline.set_completer_delims(' \t\n`~!@#$%^&*()=+[{]}\\|;:\'",<>?')

    ## Creating session information storage class
    self.session = controlsession()

    self.sshfiler = sshfiler.SSHFiler()
    try:
      self.sshfiler.reconnect()
    except Exception as err:
      logger.printwarn("Error message emitted when logging to remote host, all files will be saved locally until new login has been provided!")
      logger.printerr( str(err) )

    ## Creating the gcoder/board/camcontrol instances
    try:
      self.gcoder = gcoder.GCoder()
    except Exception as err:
      logger.printwarn(("Error message emitted when setting up printer "
                        "interface"))
      logger.printwarn(str(err))

    try:
      self.board = board.Board()
    except Exception as err:
      logger.printwarn("Error message emitted when setting up Board type")
      logger.printerr(str(err))

    try:
      self.visual = visual.Visual()
    except Exception as err:
      logger.printwarn("Error message emitted when setting up cameras")
      logger.printerr(str(err))

    try:
      self.trigger = trigger.Trigger()
    except Exception as err:
      logger.printwarn("Error message emitted when setting up GPIO interface")
      logger.printerr(str(err))

    try:
      self.readout = readout.readout(self)
    except Exception as err:
      logger.printwarn("Error message emitted when setting up I2C interface")
      logger.printerr(str(err))


  def postcmd(self, stop, line):
    logger.printmsg("")  # Printing extra empty line for aesthetics

  def get_names(self):
    """
    Overriding the the original get_names command to allow for the dynamic
    introduced commands to be listed.
    """
    return dir(self)

  def do_exit(self, line):
    sys.exit(0)

  def help_exit(self):
    "Exit program current session"

  # running commands listed in the a file requires the onecmd() method. So it
  # cannot be declared using an external class.
  def do_runfile(self, line):
    """
    usage: runfile <file>

    Executing commands listed in a file. This should be used for testing. And
    not used extensively.
    """
    if len(line.split()) != 1:
      logger.printerr("Please only specify one file!")
      return

    if not os.path.isfile(line):
      logger.printerr("Specified file could not be opened!")
      return

    with open(line) as f:
      for cmdline in f.readlines():
        self.onecmd(cmdline.strip())
    return

  def complete_runfile(self, text, line, start_index, end_index):
    return globcomp(text)


class controlcmd():
  """
  The control command is the base interface for defining a command in the
  terminal class, the instance do, callhelp and complete functions corresponds
  to the functions do_<cmd>, help_<cmd> and complete_<cmd> functions in the
  vallina python cmd class. Here we will be using the argparse class by default
  to call for the help and complete functions
  """

  def __init__(self,cmdsession):
    """
    Initializer declares an argument parser class with the class name as the
    program name and the class doc string as the description string. This
    greatly reduces the verbosity of writing custom commands.
    Each command will have accession to the cmd session, and by extension,
    every control object the could potentially be used
    """
    self.parser = argparse.ArgumentParser(
        prog=self.__class__.__name__.lower(),
        description=self.__class__.__doc__,
        add_help=False)
    self.cmd = cmdsession


  def do(self, line):
    """
    Execution of the commands automatically handles the parsing in the parse
    method. Additional parsing is allowed by overloading the parse method in the
    children classes. The actual execution of the function is handled in the run
    method.
    """
    try:
      args = self.parse(line)
    except Exception as err:
      logger.clear_update()
      logger.printerr(str(err))
      #print(err)
      return

    try:
      self.run(args)
    except Exception as err:
      logger.clear_update()
      logger.printerr(str(err))
      return

    logger.clear_update()
    return


  def callhelp(self):
    """
    Printing the help message via the ArgumentParse in built functions.
    """
    self.parser.print_help()


  def complete(self, text, line, start_index, end_index):
    """
    Auto completion of the functions. This function scans the options stored in
    the parse class and returns a string of things to return.
    - text is the word on this cursor is on (excluding tail)
    - line is the full input line string (including command)
    - start_index is the starting index of the word the cursor is at in the line
    - end_index is the position of the cursor in the line
    """
    cmdname = self.__class__.__name__.lower()
    #while line[start_index-1] == '-': start_index = start_index-1
    textargs = line[len(cmdname):start_index].strip().split()
    prevtext = textargs[-1] if len(textargs) else ""
    actions = self.parser._actions
    optstrings = [action.option_strings[0] for action in actions]

    def optwithtext():
      if text:
        return [option for option in optstrings if option.startswith(text)]
      else:
        return optstrings

    if prevtext.startswith('-'):
      ## If the previous string was already an option
      testact = [
          action for action in actions if action.option_strings[0] == prevtext
      ]
      if len(testact) != 1:
        return []
      prevact = testact[0]

      if type(prevact.type) == argparse.FileType:
        return globcomp(text)
      else:
        return [str(prevact.type), "input type"]

    else:
      return optwithtext()

  #############################
  ## The following functions should be overloaded in the inherited classes

  ## Functions that require command specific definitions
  def run(self, args):
    pass

  # Default parsing arguments, overriding the system exits exception to that the
  # session doesn't end with the user inputs a bad command. Additional parsing
  # could be achieved by overloading this methods.
  def parse(self, line):
    try:
      arg = self.parser.parse_args(line.split())
    except SystemExit as err:
      raise Exception("Cannot parse input")
    return arg


## Helper function for globbing
def globcomp(text):
  return glob.glob(text + "*")
