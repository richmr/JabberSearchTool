# standard packages
import logging
logger = logging.getLogger('jabberArchiveTools')
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
formatter = logging.Formatter('%(name)s:%(levelname)s:%(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

import base64
import hashlib
from Crypto.Cipher import AES
import pyodbc
import pytz
from datetime import datetime
import re


# some code adapted from: https://www.quickprogrammingtips.com/python/aes-256-encryption-and-decryption-in-python.html


def checkMandatoryKwargs(listOfMandatoryKwargs, kwargDict):
    for arg in listOfMandatoryKwargs:
        if arg not in kwargDict.keys():
            raise Exception("checkMandatoryKwargs: {} kwarg not found".format(listOfMandatoryKwargs))
    return True

def checkKwargsWithDefaults(dictionaryOfDefaultKwargs, kwargDict):
    for arg in dictionaryOfDefaultKwargs.keys():
        if arg in kwargDict.keys():
            # basically do nothing
            pass
        else:
            kwargDict[arg] = dictionaryOfDefaultKwargs[arg]
    return kwargDict

class jabberArchiveTools:

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        listOfMandatoryKwargs = ["pyodbc_connection"]
        checkMandatoryKwargs(listOfMandatoryKwargs, self.kwargs)
        self.cursor = self.kwargs["pyodbc_connection"].cursor()
        dictionaryOfDefaultKwargs = {
                                        "table":"jm",           # Table where the messages are
                                        "AES_key_hex":False,    # Must supply if jabber archive is encrypted
                                        "AES_IV_hex":False,     # Must supply if jabber archive is encrypted
                                        "row_count_alert_threshold":100,
                                        "encrypted_columns": ["to_jid", "from_jid", "body_string", "message_string"] # These columns must be processed
                                    }
        self.kwargs = checkKwargsWithDefaults(dictionaryOfDefaultKwargs, self.kwargs)
        self.table = self.kwargs["table"]
        self.AES_key = False
        if self.kwargs["AES_key_hex"]:
            self.AES_key = bytes.fromhex(self.kwargs["AES_key_hex"])
        self.AES_IV = False
        if self.kwargs["AES_IV_hex"]:
            self.AES_IV = bytes.fromhex(self.kwargs["AES_IV_hex"])

    # -- Encryption stuffs

    def pad(self, bytes_to_pad):
        s = bytes_to_pad
        BLOCK_SIZE = 16
        padded = s + (bytes([BLOCK_SIZE - len(s) % BLOCK_SIZE]) * (BLOCK_SIZE - len(s) % BLOCK_SIZE))
        return padded

    def unpad(self, bytes_to_clean):
        s = bytes_to_clean
        return s[:-ord(s[len(s) - 1:])]

    def encrypt_string(self, p_text):
        # returns base64 encrypted version of string (needed for searching encrypted DB)
        if not self.AES_key:
            raise Exception("You must supply a hex-encoded plain text key to decrypt a Jabber DB")
        if isinstance(p_text, str):
            p_text = p_text.encode("utf-8")
        padded_p_text = self.pad(p_text)
        freshcipher = AES.new(self.AES_key, AES.MODE_CBC, self.AES_IV)
        c_bytes = freshcipher.encrypt(padded_p_text)
        c_text = base64.b64encode(c_bytes)
        c_text = c_text.decode("utf-8")
        return c_text

    def decrypt_string(self, c_text):
        if isinstance(c_text, bytes) or isinstance(c_text, bytearray):
            c_text = c_text.encode("utf-8")
        cipher = AES.new(self.AES_key, AES.MODE_CBC, self.AES_IV)
        c_text_bytes = base64.b64decode(c_text)
        p_text = cipher.decrypt(c_text_bytes)
        p_text = self.unpad(p_text)
        return p_text.decode("utf-8")

    # -- Utility

    def processStringForQuery(self, in_string):
        # Basically checks if we are supposed to encrypt this, then does it
        # otherwise returns the orig
        if not in_string:
            return in_string
        out_string = in_string
        if self.AES_key:
            out_string = self.encrypt_string(in_string)
        return out_string

    def processStringFromResult(self, in_string):
        # might be null or none
        if not in_string:
            return in_string
        out_string = in_string
        if self.AES_key:
            out_string = self.decrypt_string(in_string)
        return out_string

    def getHTMLFromMessage(self, message_string):
        # takes a message_string and then returns the HTML only from it
        regex = re.compile("(<html.+<\/html>)")
        m = regex.search(message_string)
        if m:
            return m.group()
        else:
            return False

    # DB searches

    def checkRowCountForQuery(self):
        # uses the search in the cursor and checks result size
        # assumes the query only has one row return and that is a count
        # uses a ValueError with the found row count
        row = self.cursor.fetchone()
        if row[0] > self.kwargs["row_count_alert_threshold"]:
            raise ValueError(row[0])
        return True

    def makeTimeSearchString(self, startTime=False, endTime=False, lead=" and "):
        # returns something similar to:
        # sent_date > {ts '2019-12-05 20:00:00'} and  sent_date < {ts '2019-12-05 23:59:00'}
        # since this is user controlled input and this will be directly injectable, we must be strict on format
        regex = re.compile("^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
        if (startTime and not regex.match(startTime)) or (endTime and not regex.match(endTime)):
            raise SyntaxError("Times must be like 2021-02-19T17:11:00 (YYYY-MM-DDTHH:MM:SS)")

        startClause = ""
        endClause = ""
        join = ""

        if startTime and endTime:
            join = " and "

        if startTime:
            startTime = startTime.replace('T', ' ')
            startClause = "sent_date >= {{ts '{}'}}".format(startTime)

        if endTime:
            endTime = endTime.replace('T', ' ')
            endClause = "sent_date <= {{ts '{}'}}".format(endTime)

        finalClause = startClause + join + endClause
        if len(finalClause) > 1:
            finalClause = lead + finalClause
        return finalClause



    def processRow(self, row):
        # returns a json of this row, decrypted as needed
        # cursor info is used implicitly
        rowDat = {}
        #colCount = 0
        columns = [column[0] for column in self.cursor.description]
        for col in columns:
            colval = row.__getattribute__(col)
            if col in self.kwargs["encrypted_columns"]:
                colval = self.processStringFromResult(colval)
            if col == "sent_date":
                orig_tz = pytz.timezone("UTC")
                colval =colval.replace(tzinfo=orig_tz)

            rowDat[col] = colval
            # colCount += 1
        return rowDat

    def getMessagesFromUser(self, username, startTime=False, endTime=False, ignore_row_count=False):
        # Returns list of dictionary of row ({colname:coldata...})
        # if ignore_row_Count = True, then user will not be warned of large responses

        q_username = self.processStringForQuery(username)
        # this needed because jabber adds a random jabber_XXXX tag after usernames, and it changes
        # 16 bytes will be reliably the same after encryption because the IV and key don't change
        q_username = q_username[:16]+'%'

        # set up the time search
        timeWhere = self.makeTimeSearchString(startTime, endTime)

        # check the row count
        if not ignore_row_count:
            self.cursor.execute("select count(from_jid) from {} where from_jid like ? {}".format(self.table, timeWhere), q_username)
            self.checkRowCountForQuery()

        self.cursor.execute("select * from {} where from_jid like ? {} order by sent_date".format(self.table, timeWhere), q_username)
        alldat = []
        row = self.cursor.fetchone()
        while row:
            # need to then filter just incase we pulled the wrong ones
            aProcessedRow = self.processRow(row)
            if aProcessedRow["from_jid"].startswith(username):
                alldat.append(aProcessedRow)
            row = self.cursor.fetchone()

        return alldat

    def getMessagesToUser(self, username, startTime=False, endTime=False, ignore_row_count=False):
        # Returns list of dictionary of row ({colname:coldata...})
        # if ignore_row_Count = True, then user will not be warned of large responses

        q_username = self.processStringForQuery(username)
        # this needed because jabber adds a random jabber_XXXX tag after usernames, and it changes
        # 16 bytes will be reliably the same after encryption because the IV and key don't change
        q_username = q_username[:16]+'%'

        # set up the time search
        timeWhere = self.makeTimeSearchString(startTime, endTime)

        # check the row count
        if not ignore_row_count:
            #self.cursor.execute("select count(from_jid) from {} where from_jid = ?".format(self.table), q_username)
            self.cursor.execute("select count(to_jid) from {} where to_jid like ? {}".format(self.table, timeWhere), q_username)
            self.checkRowCountForQuery()

        #self.cursor.execute("select * from {} where from_jid = ?".format(self.table), q_username)
        self.cursor.execute("select * from {} where to_jid like ? {} order by sent_date".format(self.table, timeWhere), q_username)
        alldat = []
        row = self.cursor.fetchone()
        while row:
            # need to then filter just incase we pulled the wrong ones
            aProcessedRow = self.processRow(row)
            if aProcessedRow["to_jid"].startswith(username):
                alldat.append(aProcessedRow)
            row = self.cursor.fetchone()

        return alldat

    def getMessagesBetweenUsers(self, user1name, user2name,  startTime=False, endTime=False, ignore_row_count=False):
        # returns the conversation between two users
        q_user1name = self.processStringForQuery(user1name)
        # this needed because jabber adds a random jabber_XXXX tag after usernames, and it changes
        # 16 bytes will be reliably the same after encryption because the IV and key don't change
        q_user1name = q_user1name[:16]+'%'

        q_user2name = self.processStringForQuery(user2name)
        # this needed because jabber adds a random jabber_XXXX tag after usernames, and it changes
        # 16 bytes will be reliably the same after encryption because the IV and key don't change
        q_user2name = q_user2name[:16]+'%'

        # set up the time search
        timeWhere = self.makeTimeSearchString(startTime, endTime)
        logger.debug("tw: {}".format(timeWhere))

        # check the row count
        if not ignore_row_count:
            totalRows = 0
            #self.cursor.execute("select count(from_jid) from {} where from_jid = ?".format(self.table), q_username)
            self.cursor.execute("select count(from_jid) from {} where ((from_jid like ? and to_jid like ?) or (from_jid like ? and to_jid like ?)) {}".format(self.table, timeWhere), q_user1name, q_user2name, q_user2name, q_user1name)
            self.checkRowCountForQuery()

        self.cursor.execute("select * from {} where ((from_jid like ? and to_jid like ?) or (from_jid like ? and to_jid like ?)) {} order by sent_date".format(self.table, timeWhere), q_user1name, q_user2name, q_user2name, q_user1name)
        alldat = []
        row = self.cursor.fetchone()
        while row:
            aProcessedRow = self.processRow(row)
            # verify right combo
            if aProcessedRow["from_jid"].startswith(user1name) and aProcessedRow["to_jid"].startswith(user2name):
                alldat.append(aProcessedRow)
            elif aProcessedRow["to_jid"].startswith(user1name) and aProcessedRow["from_jid"].startswith(user2name):
                alldat.append(aProcessedRow)
            row = self.cursor.fetchone()

        return alldat

    def getAllto_jid(self):
        # returns list of all to_jids
        self.cursor.execute("select distinct(to_jid) from {}".format(self.kwargs["table"]))
        allto_jid = []
        row = self.cursor.fetchone()
        while row:
            aProcessedRow = self.processRow(row)
            # verify right combo
            allto_jid.append(aProcessedRow["to_jid"])
            row = self.cursor.fetchone()
        return allto_jid

    def getAllFrom_jid(self):
        # returns list of all to_jids
        self.cursor.execute("select distinct(from_jid) from {}".format(self.kwargs["table"]))
        all_jid = []
        row = self.cursor.fetchone()
        while row:
            aProcessedRow = self.processRow(row)
            # verify right combo
            all_jid.append(aProcessedRow["from_jid"])
            row = self.cursor.fetchone()
        return all_jid

    def getJids(self):
        # returns cleaned list of all jid (jabber suffix is removed)
        all_jid = self.getAllto_jid()
        all_jid.extend(self.getAllFrom_jid())
        cleanedJid = []
        for jid in all_jid:
            jid = jid.split("/")[0]
            if not jid in cleanedJid:
                cleanedJid.append(jid)
        cleanedJid.sort()
        return cleanedJid

    def getAllChatRooms(self):
        allJid = self.getJids()
        chatRooms = []
        for jid in allJid:
            if "@conference" in jid:
                chatRooms.append(jid)

        return chatRooms

    def getAllUserNames(self):
        allJid = self.getJids()
        users = []
        for jid in allJid:
            if "@conference" not in jid:
                users.append(jid)

        return users

    def getChatRoomsForUser(self, username):
        # returns list of all the chat rooms a user has received messages from

        q_username = self.processStringForQuery(username)
        # this needed because jabber adds a random jabber_XXXX tag after usernames, and it changes
        # 16 bytes will be reliably the same after encryption because the IV and key don't change
        q_username = q_username[:16]+'%'

        #self.cursor.execute("select * from {} where from_jid = ?".format(self.table), q_username)
        self.cursor.execute("select distinct(from_jid) from {} where to_jid like ?".format(self.table), q_username)
        chatRooms = []
        row = self.cursor.fetchone()
        while row:
            # need to then filter just incase we pulled the wrong ones
            aProcessedRow = self.processRow(row)
            if "@conference" in aProcessedRow["from_jid"]:
                if aProcessedRow["from_jid"].split("/")[0] not in chatRooms:
                    chatRooms.append(aProcessedRow["from_jid"].split("/")[0])
            row = self.cursor.fetchone()

        return chatRooms

    def getSharedChatRoomForUsers(self, listOfUsers):
        # returns list of chatrooms all users in the list used

        # start with first user
        foundSetofRooms = set(self.getChatRoomsForUser(listOfUsers[0]))
        # now do the remaining users
        for user in listOfUsers[1:]:
            thisset = set(self.getChatRoomsForUser(user))
            foundSetofRooms = foundSetofRooms.intersection(thisset)

        return list(foundSetofRooms)

    def getSendersToUser(self, username):
        # returns list of all the recipients a user has received messages from

        q_username = self.processStringForQuery(username)
        # this needed because jabber adds a random jabber_XXXX tag after usernames, and it changes
        # 16 bytes will be reliably the same after encryption because the IV and key don't change
        q_username = q_username[:16]+'%'

        #self.cursor.execute("select * from {} where from_jid = ?".format(self.table), q_username)
        self.cursor.execute("select distinct(from_jid) from {} where to_jid like ?".format(self.table), q_username)
        chatRooms = []
        row = self.cursor.fetchone()
        while row:
            # need to then filter just incase we pulled the wrong ones
            aProcessedRow = self.processRow(row)
            if "@conference" not in aProcessedRow["from_jid"]:
                if aProcessedRow["from_jid"].split("/")[0] not in chatRooms:
                    chatRooms.append(aProcessedRow["from_jid"].split("/")[0])
            row = self.cursor.fetchone()

        return chatRooms

    def getRecipientsOfUser(self,username):
        # Who has this user sent messages to
        q_username = self.processStringForQuery(username)
        # this needed because jabber adds a random jabber_XXXX tag after usernames, and it changes
        # 16 bytes will be reliably the same after encryption because the IV and key don't change
        q_username = q_username[:16]+'%'

        #self.cursor.execute("select * from {} where from_jid = ?".format(self.table), q_username)
        self.cursor.execute("select distinct(to_jid) from {} where from_jid like ?".format(self.table), q_username)
        chatRooms = []
        row = self.cursor.fetchone()
        while row:
            # need to then filter just incase we pulled the wrong ones
            aProcessedRow = self.processRow(row)
            if "@conference" not in aProcessedRow["to_jid"]:
                if aProcessedRow["to_jid"].split("/")[0] not in chatRooms:
                    chatRooms.append(aProcessedRow["to_jid"].split("/")[0])
            row = self.cursor.fetchone()

        return chatRooms

    def getUsersForChatroom(self, chatroom_jid):
        allmessages = self.getMessagesFromUser(chatroom_jid, ignore_row_count=True)
        users = {}
        for msg in allmessages:
            thisuser = msg["to_jid"].split("/")[0]
            if thisuser not in users:
                users[thisuser] = True

        finalusers = list(users.keys())
        finalusers.sort()
        return finalusers


    def getChatRoomLog(self, chatroom_jid, startTime=False, endTime=False, ignore_row_count=False):
        """
        Get all the chats from this jid
        Current UUID = "0"
        Get a chat
            get UUID of the chat
            Same as current UUID? next (not sufficient.  Chat rooms resend when someone joins.  Need a dict table)
            New UUID?
                Add to chat log
                set current UUID to this
        """
        allmessages = self.getMessagesFromUser(chatroom_jid, startTime, endTime, ignore_row_count)
        seenUUID = {}
        chatlog = []
        # this re to get the message ID from <message from='chat558881748317483@conference-3-standaloneclusterff6b8.mpiphp.org/xxx@mpiphp.org/jabber_12137' id='f0734db9:6121:408b:a890:1e2987242cb4' to='n ..
        id_re = re.compile(" id='(.+?)' ")
        for msg in allmessages:
            idFound = False
            try:
                idFound = id_re.search(msg["message_string"])
            except:
                # print("error RE on {}".format(msg))
                pass
            if idFound:
                if idFound.group() not in seenUUID:
                    chatlog.append(msg)
                    seenUUID[idFound.group()] = True

        return chatlog

    def makeMessageDump(self, messages, filename=False, timezone='America/Los_Angeles', timefmt="%Y-%m-%d %H:%M:%S", from_jid_index=0, mode="human"):
        """
        Modes: human (readable), delim (pipe delimited )

        """
        new_tz = pytz.timezone(timezone)
        f = None
        if filename:
            f = open(filename, "w")

        for msg in messages:
            msg_time = datetime.fromtimestamp(msg["sent_date"].timestamp(), tz=new_tz)
            msg_content = msg["body_string"]
            from_jid = msg["from_jid"].split("/")[from_jid_index]
            if not msg_content:
                msg_content = "NO DATA"
            time_str = msg_time.strftime(timefmt)
            to_write = f"({time_str}) {from_jid}: {msg_content}\n"
            if mode == "delim":
                to_write = f"{time_str}|{from_jid}|{msg_content}\n"
            if f is not None:
                f.write(to_write)
            else:
                print(to_write)

        if f:
            f.close()



    def makeChatroomDump(self, messages, filename=False, timezone='America/Los_Angeles', timefmt="%Y-%m-%d %H:%M:%S"):
        self.makeMessageDump(messages, filename=filename, timezone='America/Los_Angeles', timefmt="%Y-%m-%d %H:%M:%S", from_jid_index=1)

    def makeChatLogFile(self, messages, filename, timezone='America/Los_Angeles', timefmt="%Y-%m-%d %H:%M:%S", from_jid_index=0):
        new_tz = pytz.timezone(timezone)
        with open(filename, "wb") as f:
            for msg in messages:
                htmlpart = self.getHTMLFromMessage(msg["message_string"])
                if htmlpart:
                    msg_time = datetime.fromtimestamp(msg["sent_date"].timestamp(), tz=new_tz)
                    fromline = "<h5>({}) {}:</h5>\n".format(msg_time.strftime(timefmt), msg["from_jid"].split("/")[from_jid_index])
                    f.write(fromline.encode('utf-8','ignore'))
                    htmlpart += "\n"
                    f.write(htmlpart.encode('utf-8','ignore'))

    def makeChatroomLogFile(self, messages, filename, timezone='America/Los_Angeles', timefmt="%Y-%m-%d %H:%M:%S"):
        # Only difference here is the from_jid_index.  When we split sa conference chat, the name of the actual sender is in
        # the second slot
        self.makeChatLogFile(messages, filename, timezone, timefmt, from_jid_index=1)
