# standard packages
import logging
logger = logging.getLogger('JabberSearchTool')
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
formatter = logging.Formatter('%(name)s:%(levelname)s:%(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

from jabberArchiveTools import jabberArchiveTools
import argparse
import pyodbc
import re
from datetime import datetime
import pytz
from dateutil.tz import tz
import shlex
import sys

"""
Functions:
    - dump user names - show users
    - dump chatroom names - show chatrooms
    - get recipients for user - show recipients username/chatroom
    - get chatrooms from user - show chatrooms username (also show chatrooms user1,user2,etc..)
    - get messages between users - get conversation user1,user2
    - get messages in chat room - get discussion chatroom
    - exit (end interactive)

Options
    --startTime (-s)
    --endTime (-e)
    --key
    --IV
    --ODBCConnectionString
    --tableName
    --interactive (-i)
    --timezone (-t)
    --outputType (-o) [html/text]
    --outputFilename
    --noPause
    --ignore_row_warning
    --row_warning_threshold
"""

defaultODBC = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\SQLEXPRESS;DATABASE=imarchive;Trusted_Connection=yes"
defaultKey = False
defaultIV = False
defaultTimeZone = 'America/Los_Angeles'

description = 'JabberSearchTool V0.1\n'
description += 'Michael Rich - Feb 2021\n'
description += 'Please use -h to see help!\n'

parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawTextHelpFormatter)

parser.add_argument("-s", "--startTime", type=str, help="Times must be like 2021-02-19 17:11:00 (YYYY-MM-DD HH:MM:SS)")
parser.add_argument("-e", "--endTime", type=str,  help="Times must be like 2021-02-19 17:11:00 (YYYY-MM-DD HH:MM:SS)")
parser.add_argument("--key", type=str, default=defaultKey, help="Hex encoded AES-256 key from Jabber settings")
parser.add_argument("--IV", type=str, default=defaultIV, help="Hex encoded AES-256 IV from Jabber settings")
parser.add_argument("--ODBCConnectionString", type=str, default=defaultODBC, help="Valid pyodbc connection string to Jabber archive server")
parser.add_argument("--tableName", type=str, default="jm", help="Table name with the Jabber archive")
parser.add_argument("-i", "--interactive", action='store_true', help="If set, will open an interactive prompt to send additional commands")
parser.add_argument("-t", "--timezone", type=str, default=defaultTimeZone, help="Set to valid pytz timezone to display message times in the chosen time zone")
parser.add_argument("-o", "--outputType", type=str, default="text", choices=["text","html"], help="Output type for chat log files (if no --outputFilename is specified, will print to stdout in text)")
parser.add_argument("-O", "--outputFilename", type=str, help="Filename to store the chosen chat logs")
parser.add_argument("--noPause", action="store_true", help="If set, this tool will immediately exit on completion")
parser.add_argument("--row_warning_threshold", type=int, default=500, help="This is the result size threshold, anything over this will trigger a warning to narrow search parameters (or set --ignore_row_warning)")
parser.add_argument("-I", "--ignore_row_warning", action="store_true", help="If set, this will generate results regardless of how large the result set is")

command_help = "Available command options are:\n"
command_help += "show users - Get a list of all valid users in archive\n"
command_help += "show chatrooms - Get a list of all group chat rooms in the archive\n"
command_help += "get recipients [username or chatroom] - Get a list of the recipients a user sent to, or all users in a chatroom\n"
command_help += "get chatrooms [username or user1,user2,..] - Get a list of chatrooms for this user.  If multiple users are given (separated by a comma), then will list the rooms where these users were active together\n"
command_help += "get conversation [user1 user2] - Generates the conversation between these two users.  If no --outputFilename, prints to screen.  If --outputFilename then outputs to file name\n"
command_help += "get discussion [chatroom] - Generates the group discussion in this chatroom.  If no --outputFilename, prints to screen.  If --outputFilename then outputs to file name\n"
command_help += "exit - Closes this Jabber archive search session\n"
command_help += "In interactive mode, you can also specify options -s,-e,-t,-o,-O, and -I\n"

parser.add_argument("command", nargs="+", help=command_help)

# initial argument parse
args = parser.parse_args()

def showUsers(re_object, jabberSearchInstance):
    allusers = jabberSearchInstance.getAllUserNames()
    if len(allusers) == 0:
        print("No users found in archive")
        return True
    for user in allusers:
        print(user)
    return True

def showChatrooms(re_object, jabberSearchInstance):
    allrooms = jabberSearchInstance.getAllChatRooms()
    if len(allrooms) == 0:
        print("No chatrooms found in archive")
        return True
    for room in allrooms:
        print(room)
    return True

def getRecipients(re_object, jabberSearchInstance):
    user = re_object.groups()[0]
    recipients = []
    if "@conference" not in user:
        recipients = jabberSearchInstance.getRecipientsOfUser(user)
    else:
        recipients = jabberSearchInstance.getUsersForChatroom(user)
    if len(recipients) == 0:
        print("No recipients for this user found.")
        return True
    for person in recipients:
        print(person)
    return True

def getChatrooms(re_object, jabberSearchInstance):
    user = re_object.groups()[0]
    # may be a comma delimited list
    userlist = user.split(",")
    chatrooms = []
    if len(userlist) == 1:
        chatrooms = jabberSearchInstance.getChatRoomsForUser(userlist[0])
    else:
        chatrooms = jabberSearchInstance.getSharedChatRoomForUsers(userlist)

    if len(chatrooms) > 0:
        for room in chatrooms:
            print(room)
    else:
        print("No chatrooms found")

    return True

def getConversation(re_object, jabberSearchInstance):
    user1 = re_object.groups()[0]
    user2 = re_object.groups()[1]
    startTime = False
    #logger.debug("s: {}, e: {}".format(args.startTime, args.endTime))
    if args.startTime:
        startTime = fixTimezoneForSearchParameters(args.startTime)
    endTime = False
    if args.endTime:
        endTime = fixTimezoneForSearchParameters(args.endTime)
    #logger.debug("s: {}, e: {}".format(startTime, endTime))

    try:
        messages = jabberSearchInstance.getMessagesBetweenUsers(user1, user2, startTime=startTime, endTime=endTime, ignore_row_count=args.ignore_row_warning)
        if len(messages) == 0:
            print("No conversation found for the search parameters")
            return True
        logger.debug("num msg: {}".format(len(messages)))
        if args.outputFilename:
            if args.outputType == "text":
                jabberSearchInstance.makeMessageDump(messages, filename=args.outputFilename, timezone=args.timezone)
            elif args.outputType == "html":
                jabberSearchInstance.makeChatLogFile(messages, filename=args.outputFilename, timezone=args.timezone)
            else:
                raise Exception("Unknown filetype {} specified by -o".format(args.outputType))
            print("Log saved to {}".format(args.outputFilename))
        else:
            jabberSearchInstance.makeMessageDump(messages, timezone=args.timezone)
    except ValueError as badnews:
        print("Your search will return {} rows.  Either reduce the time frame with -s and -e, or specify --ignore_row_warning".format(badnews))

    return True

def getDiscussion(re_object, jabberSearchInstance):
    chatroom = re_object.groups()[0]
    startTime = False
    logger.debug("s: {}, e: {}".format(args.startTime, args.endTime))
    if args.startTime:
        startTime = fixTimezoneForSearchParameters(args.startTime)
    endTime = False
    if args.endTime:
        endTime = fixTimezoneForSearchParameters(args.endTime)
    logger.debug("s: {}, e: {}".format(startTime, endTime))

    try:
        messages = jabberSearchInstance.getChatRoomLog(chatroom, startTime=startTime, endTime=endTime, ignore_row_count=args.ignore_row_warning)
        if len(messages) == 0:
            print("No discussion found for the search parameters")
            return True
        logger.debug("num msg: {}".format(len(messages)))
        if args.outputFilename:
            if args.outputType == "text":
                jabberSearchInstance.makeChatroomDump(messages, filename=args.outputFilename, timezone=args.timezone)
            elif args.outputType == "html":
                jabberSearchInstance.makeChatroomLogFile(messages, filename=args.outputFilename, timezone=args.timezone)
            else:
                raise Exception("Unknown filetype {} specified by -o".format(args.outputType))
            print("Log saved to {}".format(args.outputFilename))
        else:
            jabberSearchInstance.makeChatroomDump(messages, timezone=args.timezone)
    except ValueError as badnews:
        print("Your search will return {} rows.  Either reduce the time frame with -s and -e, or specify --ignore_row_warning".format(badnews))

    return True


def fixTimezoneForSearchParameters(time_in):
    # Jabber archive is in UTC, these search parameters will likely be in the timezone specified in the arguments
    # need to correct them for UTC
    # needed help from: https://github.com/stub42/pytz/issues/12
    regex = re.compile("^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
    if not regex.match(time_in):
        raise SyntaxError("Times must be like 2021-02-19 17:11:00 (YYYY-MM-DD HH:MM:SS)")
    time_fmt_str = "%Y-%m-%d %H:%M:%S"
    time_in_dt = datetime.strptime(time_in, time_fmt_str)
    orig_tz = tz.gettz(args.timezone) #pytz.timezone(atz)
    time_in_dt = time_in_dt.replace(tzinfo=orig_tz)
    # convert to UTC
    time_out_dt = datetime.fromtimestamp(time_in_dt.timestamp(), tz=pytz.timezone("UTC"))
    return time_out_dt.strftime(time_fmt_str)

def routeCommand(userinput, re_dictionary, jabberSearchInstance):
    goodCommand = False
    for regex in re_dictionary.keys():
        are  = re.compile(regex)
        are_match = are.match(userinput)
        if are_match:
            goodCommand = re_dictionary[regex](are_match, jabberSearchInstance)
            break
    return goodCommand

commandRe_dictionary = {
                        "show users":showUsers,
                        "show chatrooms":showChatrooms,
                        "get recipients (.+)":getRecipients,
                        "get chatrooms (.+)":getChatrooms,
                        "get conversation (.+) (.+)":getConversation,
                        "get discussion (.+)":getDiscussion
                        }

try:
    # start DB connection
    if not args.ODBCConnectionString:
        sys.exit("Please provide a valid ODBC connection string with --ODBCConnectionString")

    cnxn = pyodbc.connect(args.ODBCConnectionString)
    # Start jabs session
    jabberConfig = {
                    "pyodbc_connection":cnxn,
                    "table":args.tableName,
                    "AES_key_hex":args.key,
                    "AES_IV_hex":args.IV,
                    "row_count_alert_threshold":args.row_warning_threshold,
                    }
    jabs = jabberArchiveTools(**jabberConfig)

    # begin the loop
    while True:
        nextcommand = ""
        commandString = [str(i) for i in args.command]
        commandString = " ".join(commandString)
        print("Processing command {}".format(commandString))

        if args.command[0] == "exit":
            break
        if not routeCommand(commandString, commandRe_dictionary, jabs):
            print("Unrecognized command '{}'".format(commandString))
            print(command_help)
        if args.interactive:
            nextcommand = ""
            nextcommand = input("> ")
            nextcommand_list = shlex.split(nextcommand)
            # Need to add interactive back in
            nextcommand_list.append("-i")
            if args.ignore_row_warning:
                nextcommand_list.append("-I")
        elif args.noPause:
            break
        else:
            wait = input("Press enter to exit")
            break

        args = parser.parse_args(nextcommand_list)

except Exception as badnews:
    #raise badnews
    print("Unable to complete search: {}".format(badnews))
    if not args.noPause:
        wait = input("Press enter to exit")
