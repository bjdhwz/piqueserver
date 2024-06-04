"""
In-game account system. Allows players to register, and admins to assign groups defined in [rights] subsection of the config file.
Automatically logs player in if IP address doesn't change.
First registered account will be added to 'admin' group.

Commands
^^^^^^^^

* ``/reg <password> <repeat password>`` register on the server
* ``/login <password>`` log in if you're registered on the server

.. codeauthor:: Liza
"""

from datetime import datetime
import hashlib, os, sqlite3
from piqueserver.commands import command
from piqueserver.config import config

db_path = os.path.join(config.config_dir, 'sqlite.db')
con = sqlite3.connect(db_path)
cur = con.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS users(user, password, user_type, reg_dt, reg_session)')


def hashstr(s):
    sha2 = hashlib.sha256()
    sha2.update(bytes(s, 'utf8'))
    return sha2.hexdigest()

@command('register', 'reg')
def register(connection, password, password_repeat):
    """
    Register on the server
    /reg <password> <repeat password>
    """
    q = cur.execute('SELECT user FROM users WHERE user = ? COLLATE NOCASE', (connection.name,)).fetchone()
    if q:
        return "Name %s is already registered. If it wasn't you, please pick a different name" % q[0]
    if password != password_repeat:
        return "Passwords don't match, please try again"
    is_not_empty = cur.execute('SELECT EXISTS (SELECT 1 FROM users)').fetchone()[0]
    if is_not_empty:
        cur.execute('INSERT INTO users VALUES(?, ?, ?, ?, ?)', (connection.name, hashstr(password), 'player', datetime.now().isoformat(sep=' ')[:16], connection.session))
    else:
        cur.execute('INSERT INTO users VALUES(?, ?, ?, ?, ?)', (connection.name, hashstr(password), 'admin', datetime.now().isoformat(sep=' ')[:16], connection.session))
    con.commit()
    connection.protocol.notify_admins("%s registered successfully" % connection.name)
    return "Registration successful. Use /login <password> to log in"

@command()
def login(connection, password):
    """
    Log in if you're registered on the server
    /login <password>
    """
    if connection.logged_in:
        return "You're already logged in"
    else:
        q = cur.execute('SELECT password, user_type FROM users WHERE user = ? COLLATE NOCASE', (connection.name,)).fetchone()
        if q:
            password_hash, user_type = q
            if hashstr(password) == password_hash:
                cur.execute('UPDATE sessions SET logged_in = ? WHERE id = ?', (True, connection.session))
                con.commit()
                connection.logged_in = True
                if user_type:
                    connection.on_user_login(user_type, True)
                connection.protocol.notify_admins("%s logged in successfully" % connection.name)
                return "Logged in successfully"
            else:
                if connection.login_retries is None:
                    connection.login_retries = connection.protocol.login_retries - 1
                else:
                    connection.login_retries -= 1
                if not connection.login_retries:
                    connection.kick("Ran out of login attempts")
                    return
                return "Invalid password - you have %s tries left" % (
        connection.login_retries)
        else:
            return "Please register using /reg <password> <repeat password>"

@command(admin_only=True)
def group(connection, player=None, user_type=None):
    """
    /group - get your info
    /group <player> - get player's info
    /group <player> <user_type> - set player's user_type, as defined in [rights] subsection of the config file
    /group <player> admin - give player admin rights (such as access to 'admin_only=True' commands)
    /group <player> trusted - make player trusted
    """
    if not player:
        player = connection.name
    q = cur.execute('SELECT user, user_type, reg_dt, reg_session FROM users WHERE user = ? COLLATE NOCASE', (player,)).fetchone()
    if q:
        if user_type:
            cur.execute('UPDATE users SET user_type = ? WHERE user = ? COLLATE NOCASE', (user_type, player))
            con.commit()
            connection.protocol.notify_admins("%s changed %s's user_type to %s" % (connection.name, player, user_type))
            return "Account has been modified"
        else:
            user, user_type, reg_dt, reg_session = q
            return "%s | group: %s | registered %s session ID%s" % (user, user_type, reg_dt, reg_session)
    else:
        return "Account not found"

@command('unregister', 'unreg', admin_only=True)
def unregister(connection, player):
    """
    Removes player's account, letting them register again
    /unreg <player>
    """
    if cur.execute('SELECT user FROM users WHERE user = ? COLLATE NOCASE', (player,)).fetchone():
        cur.execute('DELETE FROM users WHERE user = ? COLLATE NOCASE', (player,))
        con.commit()
        connection.protocol.notify_admins("%s removed %s's account" % (connection.name, player))
        return "Account has been removed"
    else:
        return "Account not found"


def apply_script(protocol, connection, config):
    class AuthProtocol(protocol):

        def notify_player(self, msg, name):
            for player in self.players.values():
                if player.name.lower() == name.lower():
                    player.send_chat(msg)

        def notify_admins(self, msg):
            for player in self.players.values():
                if player.admin:
                    player.send_chat('[ADMIN] ' + msg)

    class AuthConnection(connection):
        connection.logged_in = False

        def on_login(self, name):
            connection.on_login(self, name)
            q = cur.execute('SELECT ip, logged_in FROM sessions WHERE user = ? ORDER BY id DESC LIMIT 1, 1 COLLATE NOCASE', (self.name,)).fetchone()
            if q:
                last_ip, logged_in = q
                if last_ip == self.address[0] and logged_in == True:
                    self.logged_in = True
                    user_type = cur.execute('SELECT user_type FROM users WHERE user = ? COLLATE NOCASE', (self.name,)).fetchone()
                    if user_type:
                        self.on_user_login(user_type[0], True)
                    cur.execute('UPDATE sessions SET logged_in = ? WHERE id = ?', (True, self.session))
                    con.commit()

    return AuthProtocol, AuthConnection
