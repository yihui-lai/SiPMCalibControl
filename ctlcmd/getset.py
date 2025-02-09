import ctlcmd.cmdbase as cmdbase
import cmod.logger as log
from cmod.readout import readout
import argparse
import re


class set(cmdbase.controlcmd):
  """
  Setting session parameters
  """
  def __init__(self, cmd):
    cmdbase.controlcmd.__init__(self, cmd)
    self.parser.add_argument(
        '-boardtype',
        type=argparse.FileType(mode='r'),
        help=('Setting board type via a configuration json file that lists '
              'CHIP_ID with x-y-coordinates.'))
    self.parser.add_argument(
        '-printerdev',
        type=str,
        help=('Device path for the 3d printer. Should be something like '
              '`/dev/tty<SOMETHING>`.'))
    self.parser.add_argument(
        '-camdev',
        type=str,
        help=('Device path for the primary camera, should be something like '
              '/dev/video<index>.'))
    self.parser.add_argument('-remotehost',
                             type=str,
                             help='Connecting to remote host for file transfer')
    self.parser.add_argument('-remotepath',
                             type=str,
                             help='Remote directory to save files to')
    self.parser.add_argument(
        '-picodevice',
        type=str,
        help=('The serial number of the pico-tech device for dynamic light '
              'readout'))
    self.parser.add_argument(
        '-readout',
        type=int,
        choices=[readout.MODE_ADC, readout.MODE_PICO, readout.MODE_NONE],
        help='Setting readout mode of the current session')
    self.parser.add_argument('-action',
                             type=argparse.FileType(mode='r'),
                             help='List of short hands for setting user prompts')

  def run(self, args):
    if args.boardtype:
      self.set_board(args)
    if args.camdev:
      self.set_camera(args)
    if args.printerdev:
      self.set_printer(args)
    if args.remotehost:
      self.set_host(args)
    if args.remotepath:
      self.sshfiler.setremotepath(args.remotepath)
    if args.picodevice:
      self.set_picodevice(args)
    if args.readout:
      self.readout.set_mode(args.readout)
    if args.action:
      self.action.add_json(args.action.name)

  def set_board(self, args):
    try:
      self.board.set_boardtype(args.boardtype.name)
    except Exception as err:
      log.printerr(str(err))
      log.printwarn('Board type setting has failed, skipping over setting')

  def set_camera(self, args):
    if args.camdev == self.visual.dev_path:
      pass
    try:
      self.visual.init_dev(args.camdev)
    except Exception as err:
      log.printerr(str(err))
      log.printwarn('Initializing webcam has failed, skipping over setting')

  def set_printer(self, args):
    if args.printerdev == self.gcoder.dev_path:
      pass
    try:
      self.gcoder.initprinter(args.printerdev)
      printset = self.gcoder.getsettings()
      printset = printset.split('\necho:')
      for line in printset:
        log.printmsg(log.GREEN('[PRINTER]'), line)
    except Exception as err:
      log.printerr(str(err))
      log.printwarn('Failed to setup printer, skipping over settings')

  def set_host(self, args):
    try:
      self.sshfiler.reconnect(args.remotehost)
    except Exception as err:
      log.printerr(str(err))
      log.printwarn('Failed to establish connection remote host')

  def set_picodevice(self, args):
    try:
      self.pico.init()
    except Exception as err:
      log.printerr(str(err))
      log.printwarn('Picoscope device is not properly set!')


class get(cmdbase.controlcmd):
  """
  Printing out the session parameters, and equipment settings.
  """
  def __init__(self, cmd):
    cmdbase.controlcmd.__init__(self, cmd)
    self.parser.add_argument('--boardtype', action='store_true')
    self.parser.add_argument('--printerdev', action='store_true')
    self.parser.add_argument('--camdev', action='store_true')
    self.parser.add_argument('--origchip', action='store_true')
    self.parser.add_argument('--align', action='store_true')
    self.parser.add_argument('--pico', action='store_true')
    self.parser.add_argument('--readout', action='store_true')
    self.parser.add_argument('--action', action='store_true')

    self.parser.add_argument('-a', '--all', action='store_true')

  def run(self, args):
    if args.boardtype or args.all:
      self.print_board()
    if args.printerdev or args.all:
      self.print_printer()
    if args.camdev or args.all:
      log.printmsg(log.GREEN('[CAM DEV]'), str(self.visual.dev_path))
    if args.align or args.all:
      self.print_alignment()
    if args.pico or args.all:
      self.pico.printinfo()
    if args.readout or args.all:
      self.print_readout()
    if args.action or args.all:
      for key in self.action.shorthands():
        log.printmsg(log.GREEN('[ACTIONS]'), key + ' | ' + self.action.map[key])

  def print_board(self):
    header = log.GREEN('[BOARDTYPE]')
    msg_format = 'Chip:{0:>4s} | x:{1:5.1f}, y:{2:5.1f}'
    log.printmsg(header, str(self.board.boardtype))
    log.printmsg(header, 'Board ID: ' + self.board.boardid)
    for chip in self.board.chips():
      msg = msg_format.format(chip, self.board.orig_coord[chip][0],
                              self.board.orig_coord[chip][1])
      log.printmsg(header, msg)

  def print_printer(self):
    header = log.GREEN('[PRINTER]')
    log.printmsg(header, 'device: ' + str(self.gcoder.dev_path))
    log.printmsg(
        header, 'current coordinates: x{0:.1f} y{1:.1f} z{2:0.1f}'.format(
            self.gcoder.opx, self.gcoder.opy, self.gcoder.opz))

  def print_camera(self):
    header = log.GREEN('[CAMERA]')
    log.printmsg(header, str(self.visual.dev_path))

  def print_alignment(self):
    lumi_header = log.GREEN('[LUMI_ALIGN]')
    matrix_header = log.GREEN('[VIS_MATRIX]')
    vis_header = log.GREEN('[VIS__ALIGN]')
    chip_format = log.YELLOW(' CHIP{0:3d}')
    for chip in self.board.chips():
      chip_str = chip_format.format(int(chip))
      for z in self.board.lumi_coord[chip].keys():
        log.printmsg(
            lumi_header + chip_str,
            'x:{0:.2f}+-{1:.2f} y:{2:.2f}+-{3:.2f} | at z={4:.1f}'.format(
                self.board.vis_coord[chip][z][0],
                self.board.vis_coord[chip][z][2],
                self.board.vis_coord[chip][z][1],
                self.board.vis_coord[chip][z][3], z))
      for z in self.board.visM[chip].keys():
        log.printmsg(matrix_header + chip_str, '{0} | at z={1:.1f}'.format(
            self.board.visM[chip][z], z))
      for z in self.board.vis_coord[chip].keys():
        log.printmsg(
            vis_header + chip_str, 'x:{0:.2f} y:{1:.2f} | at z={2:.1f}'.format(
                self.board.vis_coord[chip][z][0],
                self.board.vis_coord[chip][z][1], z))

  def print_readout(self):
    log.printmsg(
      log.GREEN('[READOUT]'),
      'PICOSCOPE' if self.readout.mode == readout.MODE_PICO else \
      'ADC CHIP'  if self.readout.mode == readout.MODE_ADC  else \
      'PREDEFINED MODEL')

  def print_action(self):
    header = log.GREEN('[ACTION]')
    msg_format = log.YELLOW('{0}') + ' | {1}'
    for key in self.action.shorthands():
      msg = msg_format.format(key, self.action.map[key])
      log.printmsg(header, msg)


class getcoord(cmdbase.controlcmd):
  """
  Printing current gantry coordinates
  """
  LOG = log.GREEN('[GANTRY-COORD]')

  def __init__(self, cmd):
    cmdbase.controlcmd.__init__(self, cmd)

  def run(self, args):
    self.printmsg('x:{0:.1f} y:{1:.1f} z:{2:.1f}'.format(
        self.gcoder.opx, self.gcoder.opy, self.gcoder.opz))


class savecalib(cmdbase.controlcmd):
  """
  Saving current calibration information into a json file
  """
  LOG = log.GREEN('[SAVE_CALIB]')
  def __init__(self, cmd):
    cmdbase.controlcmd.__init__(self, cmd)
    self.parser.add_argument('-f',
                             '--file',
                             type=argparse.FileType('w'),
                             required=True,
                             help='File to save the calibration events to')

  def parse(self, line):
    args = cmdbase.controlcmd.parse(self, line)
    if not args.file:
      raise Exception('File name must be specified')
    return args

  def run(self, args):
    self.printmsg('Saving calibration results to file [{0}]'.format(
      args.file.name))
    self.board.save_calib_file(args.file.name)


class loadcalib(cmdbase.controlcmd):
  """
  Loading calibration information from a json file
  """
  def __init__(self, cmd):
    cmdbase.controlcmd.__init__(self, cmd)
    self.parser.add_argument(
        '-f',
        '--file',
        type=argparse.FileType('r'),
        help='File to load the calibration information from')

  def parse(self, line):
    args = cmdbase.controlcmd.parse(self, line)
    if not args.file:
      raise Exception('Filename must be specified')
    return args

  def run(self, args):
    self.board.load_calib_file(args.file.name)


class lighton(cmdbase.controlcmd):
  """
  Turning the LED lights on.
  """
  def __init__(self, cmd):
    cmdbase.controlcmd.__init__(self, cmd)

  def run(self, args):
    self.trigger.light_on()


class lightoff(cmdbase.controlcmd):
  """
  Turning the LED lights on.
  """
  def __init__(self, cmd):
    cmdbase.controlcmd.__init__(self, cmd)

  def run(self, line):
    self.trigger.light_off()


class promptaction(cmdbase.controlcmd):
  """
  Displaying message that requires manual intervention.
  """
  def __init__(self, cmd):
    cmdbase.controlcmd.__init__(self, cmd)
    self.parser.add_argument(
        'string',
        nargs=1,
        type=str,
        help=('String of message to show (program is paused until Enter key '
              'is pressed). This can either be a short hand that is defined '
              'using the loadaction command (use the listaction command to '
              'get a list) or a raw string message that is to be shown on the '
              'screen'))

  def parse(self, line):
    return cmdbase.controlcmd.parse(self, line)

  def run(self, args):
    def color_change(x):
      """
      Formatting the output for clarity of what the user should be doing.
      """
      if x == '[ON]':
        return log.GREEN(x)
      if x == '[OFF]':
        return log.RED(x)
      if re.match(r'\[[\d\.]+[a-zA-Z]*\]', x):
        return log.GREEN(x)
      if x.isupper():
        return log.YELLOW(x)
      return x

    self.init_handle()

    msg = self.action.map[args.string[0]] \
          if args.string[0] in self.action.shorthands() \
          else ' '.join(args.string)

    msg = ' '.join([color_change(x) for x in msg.split()])
    log.printmsg(log.GREEN('    THE NEXT STEP REQUIRES USER INTERVENTION'))
    log.printmsg('    > ' + msg)

    input_text = ''
    while input_text != args.string[0]:
      self.check_handle(args)
      input_text = input(
          log.GREEN('    TYPE [%s] to continue...') % args.string[0])
