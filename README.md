# JabberSearchTool
As a security guy, I am often asked to help do pulls of data for legal review/HR issues.  I have not been asked, so far, to a do a pull of our Cisco Jabber logs but I wanted to be prepared.  To my surprise I wasn't able to find a professional, supported tool to do this (even after asking my Cisco rep).  So I wrote this command line tool to assist me.  

Now there STILL isn't a professional, supported tool but there is this at least.

A quick warning: like all access-privileged IT folks, I have the ability to read others' emails, enter folders, see network activity, etc.  But nothing has tempted me to explore others' activity like the ability to read their Jabber chats after I finished this tool.  Be good; don't abuse your access (and don't get fired).

## Pre-requisites
- HR Permission
  - Don’t dig through folks’ messages without permission.
  - This is really to support HR and/or legal actions and not as entertainment
- DB Permissions
  - You will need READ permission to the IMArchive DB, on whatever server is hosting it
  - You will need the correct pyodbc string to connect to that DB.  Examples:
    - Windows AD connected authentication: `DRIVER={ODBC Driver 17 for SQL Server};SERVER=jabberDBServer;DATABASE=imarchive;Trusted_Connection=yes`
    - SQL-Native accounts: `DRIVER={ODBC Driver 17 for SQL Server};SERVER=jabberDBServer;DATABASE=imarchive;UID=username;PWD=password`
  - I highly recommend copying a few thousand rows of the Jabber DB to your local machine for testing, and then use: `DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\SQLEXPRESS;DATABASE=imarchive;Trusted_Connection=yes`
- Operating system
  - This tool has only been tested on Windows 10 and MS SQL Server
- Python
 - You will need at least a python 3.7 installation
 - Your python environment will need these packages:
   - Not always present:
     - pyodbc
     - pytz
     - dateutil
  - Usually installed by default:
    - argparse
    - re
    - datetime
    - base64
    - hashlib
    - crypto
    - shlex
  - The Anaconda installation for Windows had all of these packages by default
- The toolset
  - Because I am too lazy to make a pip installer, make sure jabberArchiveTools.py and JabberSearchTool.py are in the same directory
- Decryption keys
  - If your Cisco Jabber instance has been configured for encryption, you will need to recover the AES-256 key and IV from the Cisco Unified Presence Admin portal.
  - Recovering the keys is outside of the scope of this tool.  Please consult current Cisco documentation (try searching for Instant Messaging Compliance Guide)
  - Cisco, by default, does NOT include the keys as part of the SQL Server table build which is why this tool needs the keys to "manually" decrypt the row data
  - Keys and IV are hex-encoded and look like: `key='5c48c518ae9e3fc926d00bb272a0614a993a859f25423b3b30f1ef7284bc3272'` and `iv='54b80e505c3d835e39ccce8bd6b24c01'`
  - Relax.  Those are totally randomly generated hex strings put here as an example
- A little bit of patience
  - My company is pretty small and the Jabber archive database is still quite large; queries take a long time.
  - Always specify `--startTime "YYYY-MM-DD HH:MM:SS" --endTime "YYYY-MM-DD HH:MM:SS"` as soon as you know what time frame you are interested in to keep search times reduced.
  - Again, I highly recommend making a local copy of a few thousand rows and testing this tool against that copy before accessing the official database.

## Starting the tool
If you are using MS AD-integrated security on MS SQL, and the account that has been given access to the DB is not the one you use to log in to your workstation, you will need to `runas` those credentials:
- Open a python-capable command window.  I use the Anaconda prompt.
- `runas /env /user:ADDomain\privaccount "python JabberSearchTool.py -I -i get recipients user@domain"`
- Make sure you specify “/env” to run out of the directory you are currently in.
- I also specified `—i` (interactive) here so the tool provides a prompt to continue queries.  This is useful so your privileged session stays open.
- You have to specify your initial command and then the tool will enter interactive mode.
All commands and option flags are described below.

## Commands
The tool has a few basic searches it can do:
- `show users` - Get a list of all valid users in archive.  
  - Usernames generally take the form of their username@domain.  But if you are having issues, dump this list of users and search through it
- `show chatrooms` - Get a list of all group chat rooms in the archive
  - Chatrooms have very odd names like: io393961768317683@conference-3-standaloneclusterff6b8.domain
  - You need the full name to search for it
- `get recipients [username or chatroom]` - Get a list of the recipients a user sent to, or all users in a chatroom.  Examples:
  - `get recipients user@domain`
  - `get recipients io393961768317683@conference-3-standaloneclusterff6b8.domain`
- `get chatrooms [username or user1,user2,..]` - Get a list of chatrooms for this user.  If multiple users are given (separated by a comma), then will list the rooms where these users were active together
  - Useful if you need to figure out where folks are talking
- `get conversation [user1 user2]` - Generates the conversation between these two users.  
  - Conversations can be pretty large!  You will want to specific `–startTime` and --`endTime`
  - If no --`outputFilename`, prints to screen.  If --`outputFilename filename` then outputs to filename
  - Will output a flat text or html file based on the `–outputType` setting (text is default)
- `get discussion [chatroom]` - Generates the group discussion in this chatroom.  
  - Chatroom conversations can be quite large!  You may want to specific `–startTime` and --`endTime`
  - If no --outputFilename, prints to screen.  If `--outputFilename filename` then outputs to filename
  - Will output a flat text or html file based on the `--outputType` setting (text is default)
- `exit` - Closes this Jabber archive search session
- In interactive mode, you can also specify options -s,-e,-t,-o,-O, and -I at the action prompt

## Search Options
- `-s time` or `--startTime time`: Times must be like 2021-02-19 17:11:00 (YYYY-MM-DD HH:MM:SS)
- `-e time`, `--endTime time`: Times must be like 2021-02-19 17:11:00 (YYYY-MM-DD HH:MM:SS)
- `--key key`: Hex encoded AES-256 key from Jabber settings.  Though this is "optional", you will need it if the database is encrypted
- `--IV iv`: Hex encoded AES-256 IV from Jabber settings.  
- `--ODBCConnectionString string`: Valid pyodbc connection string to the Jabber archive server.  This is an "optional" argument only because the version I use of this command at work has the correct one for my environment hard coded in to the tool.  JabberSearchTool will not work without this argument
- `--tableName tablename`: Table name with the Jabber archive.  “jm” is used by default
  - *Warning: This parameter can result in direct SQL injection.  If this is controlled by a non-trusted user (i.e. not you) then you must sanitize this parameter.*
- `-i`, `--interactive`: If set, will open an interactive prompt to send additional commands
- `-t tz`, `--timezone tz`: Set to valid pytz timezone to display message times in the chosen time zone.  Defaults to 'America/Los_Angeles'
- `-o [text/html]`, `--outputType [text/html]`: choices are "text" or "html", sets the output type for chat log files (if no --outputFilename is specified, will print to stdout in text)
- `-O`, `--outputFilename`: Filename to store the chosen chat logs
- `--noPause`: If set, the tool will immediately exit on completion.  Leaving pause “on” is important for “runas” scenarios or the window may close before you see the results
- `--row_warning_threshold number`: This is the result size threshold, anything over this will trigger a warning to narrow search parameters (or set `--ignore_row_warning`).  The default is 500 rows
- `-I`, `--ignore_row_warning`: If set, this will generate results regardless of how large the result set is

# Example session
(commands start with **** for readability):
```
**** (base) C:\Users\user\Documents\tech\jabber>python JabberSearchTool.py --interactive get chatrooms user@domain
 Processing command get chatrooms user@domain
 chat415421941519415@conference-3-standaloneclusterff6b8.domain
 itleadershipmanagement3171976819768@conference-3-standaloneclusterff6b8.domain
 io393961768317683@conference-3-standaloneclusterff6b8.domain
 itsecurity265841687816878@conference-3-standaloneclusterff6b8.domain
**** > get discussion itsecurity265841687816878@conference-3-standaloneclusterff6b8.domain
 Processing command get discussion itsecurity265841687816878@conference-3-standaloneclusterff6b8.domain
 Your search will return 5839 rows.  Either reduce the time frame with -s and -e, or specify --ignore_row_warning
**** > -s "2020-01-20 00:00:00" -e "2020-01-21 00:00:00" get discussion itsecurity265841687816878@conference-3-standaloneclusterff6b8.domain
 Processing command get discussion itsecurity265841687816878@conference-3-standaloneclusterff6b8.domain
 No discussion found for the search parameters
**** > -s "2020-04-03 00:00:00" -e "2020-04-04 00:00:00" get discussion itsecurity265841687816878@conference-3-standaloneclusterff6b8.domain
 Processing command get discussion itsecurity265841687816878@conference-3-standaloneclusterff6b8.domain
 (2020-04-03 08:01:48) user1@domain: Good morning!
 (2020-04-03 08:07:24) user2@domain: It's all good.  space added.
 (2020-04-03 08:07:24) user1@domain: So we don't have to worry about prying eyes.
 [REDACTED RESULTS TO KEEP THIS SHORT]
 (2020-04-03 15:56:57) user2@domain: Alright I had dr pepper and peanut m&ms.  Lets do this.
**** > exit
 Processing command exit
```

 ## Oddities
 You may occasionally see this, especially on time limited searches in chat rooms:
```
(2020-04-04 14:06:53) user3@domain: lol
(2020-04-04 14:06:53) user1@domain: Cause if the vault maxes out on HD space, it will make many people sad.
(2020-04-04 14:06:53) user1@domain: I think we're ok though.
(2020-04-04 14:06:53) user1@domain: That's to the PSM server
(2020-04-04 14:06:53) user1@domain: looks like there is maximum allocated storage on the vault
(2020-04-04 14:06:53) user2@domain: Didn't you guys see my slack?
(2020-04-04 14:06:53) user3@domain: I thought ops added more storage?
(2020-04-04 14:06:53) user1@domain: no, maybe?
(2020-04-04 14:06:53) user1@domain: which channel
(2020-04-04 14:06:53) user2@domain: security team
(2020-04-04 14:06:53) user1@domain: Yep 4
(2020-04-04 14:06:53) user1@domain: Postponed.
(2020-04-04 14:06:53) user1@domain: talk to ya then
(2020-04-04 14:06:53) user3@domain: ok
(2020-04-04 14:06:53) user2@domain: Alright I had dr pepper and peanut m&ms.  Lets do this.
```
These were all delivered at exactly the same time, which means they were actually resent to someone who re-signed back in to the chat room.  This is difficult to filter out, but if you see a lot of messages sent at the same time, then they are repeats.

Also, sometimes chats are sent with no message.  That shows up as “NO DATA” in the log

The tool cannot reproduce screenshots or sent files, they are not retained in the database.

## Feature Request and Bug Reporting
Feel free to contact me through GitHub, but I make no promises of my ability to help you with bugs or features.  As stated in the license file:

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

That said I do get excited to solve interesting problems.
