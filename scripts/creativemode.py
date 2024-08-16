"""
1) Disables flag capture
2) Hides tents and intel from the map
3) Disables grenade damage
4) Infinite blocks
5) Fast travel command
6) Enables teamkill for Blue team and disables all killing for Green team, creating 'PVP' and 'Peace' teams

Commands
^^^^^^^^

* ``/flag <1|2> <hide>`` bring intel to your current location or hide it

.. codeauthor:: Liza
"""

from piqueserver.commands import command, target_player
from pyspades import contained as loaders
from pyspades.common import coordinates
from twisted.internet.task import LoopingCall

HIDE_POS = (-256, -256, 63)

ALL_SECTORS = [chr(x // 8 + ord('A')) + str(x % 8 + 1) for x in range(64)]


def do_move(connection, sector, silent=False, top=False):
    x, y = coordinates(sector)
    x += 32
    y += 32
    if top:
        for i in range(64):
            if connection.protocol.map.get_solid(x, y, i):
                z = i - 2
                break
    else:
        z = connection.protocol.map.get_height(x, y) - 2
    connection.set_location((x, y, z))
    if not silent:
        connection.protocol.broadcast_chat('%s teleported to %s' % (connection.name, sector))

@command('gt', 'goto')
def gt(connection, sector):
    """
    Teleport to a sector
    /gt <sector>
    """
    sector = sector.upper()
    if sector not in ALL_SECTORS:
        return "Invalid sector. Example of a sector: A1"
    do_move(connection, sector)

@command('gts', admin_only=True)
def gts(connection, sector):
    """
    Teleport to a sector silently
    /gts <sector>
    """
    sector = sector.upper()
    if sector not in ALL_SECTORS:
        return "Invalid sector. Example of a sector: A1"
    do_move(connection, sector, True)

@command('gtop', 'go')
def gtop(connection, sector):
    """
    Teleport to a sector (always overground)
    /gtop <sector>
    """
    sector = sector.upper()
    if sector not in ALL_SECTORS:
        return "Invalid sector. Example of a sector: A1"
    do_move(connection, sector, top=True)

@command('gtops', 'gos', admin_only=True)
def gtops(connection, sector):
    """
    Teleport to a sector silently (always overground)
    /gtops <sector>
    """
    sector = sector.upper()
    if sector not in ALL_SECTORS:
        return "Invalid sector. Example of a sector: A1"
    do_move(connection, sector, True, top=True)

@command('f', 'fly')
def fly_shortcut(connection):
    """
    Enable flight
    /f
    """
    if connection.team == connection.protocol.team_1:
        return 'Fly not available in PVP team'
    else:
        connection.fly = not connection.fly
        message = 'now flying' if connection.fly else 'no longer flying'
        connection.send_chat("You're %s" % message)

@command(admin_only=True)
def flag(connection, team, hide=False):
    """
    Allows to use intel for decorative purposes
    /flag <1|2> <hide> - bring intel to your current location or hide it
    """
    if team == '1':
        flag = connection.protocol.team_1.flag
    elif team == '2':
        flag = connection.protocol.team_2.flag
    else:
        return "Usage: /flag <1|2> <hide>"

    if hide:
        flag.set(*HIDE_POS)
    else:
        x, y, z = [round(x*2)/2 for x in connection.get_location()]
        flag.set(x, y, z+2.5)
    flag.update()

@command(admin_only=True)
def tppos(connection, x, y, z):
    connection.set_location((int(x), int(y), int(z)))

@command()
def info(connection):
    """
    Display coordinates and color of the block that you're looking at
    /info
    """
    connection.info_mode = not connection.info_mode

@command()
def pingmon(connection):
    """
    Monitor latency
    /pingmon
    """
    connection.pingmon_mode = not connection.pingmon_mode
    if connection.pingmon_mode:
        connection.latency_history = [0] * 30
        connection.pingmon_loop = LoopingCall(connection.update_pingmon)
        connection.pingmon_loop.start(1)
    else:
        connection.pingmon_loop.stop()

@command('clearammo', 'ca', admin_only=True)
@target_player
def clear_ammo(connection, player):
    """
    Remove player's ammo
    /clearammo
    """
    weapon_reload = loaders.WeaponReload()
    weapon_reload.player_id = player.player_id
    weapon_reload.clip_ammo = 0
    weapon_reload.reserve_ammo = 0
    player.grenades = 0
    player.weapon_object.reset()
    player.weapon_object.set_shoot(False)
    player.weapon_object.clip_ammo = 0
    player.weapon_object.reserve_ammo = 0
    player.send_contained(weapon_reload)
    return "%s's ammo has been cleared" % player.name

def apply_script(protocol, connection, config):
    class NoCaptureConnection(connection):

        info_mode = False
        info_cur = None
        pingmon_mode = False
        latency_history = [0] * 30

        def update_pingmon(self):
            blocks = '▁▂▃▄▅▆▇█'
            if len(self.latency_history) == 30:
                self.latency_history = self.latency_history[1:]
            self.latency_history += [self.latency]
            l = self.latency_history
            base = min([x for x in l if x])
            mul = 7/(max(l)-base+1)
            l = [blocks[round((x-base)*mul)] if x else blocks[0] for x in l]
            self.send_cmsg(''.join(l) + ' ' + str(self.latency) + 'ms', 'Notice')

        def on_disconnect(self):
            try: # might already not exist when called
                self.pingmon_loop.stop()
            except:
                pass
            return connection.on_disconnect(self)

        def on_flag_take(self):
            return False

        def on_flag_drop(self):
            return False

        def on_flag_capture(self):
            return False

        def capture_flag(self):
            return False

        def on_team_join(self, team):
            if team == self.protocol.team_1:
                if self.fly:
                    self.fly = False
                    self.send_chat("You're no longer flying")
            return team

        def on_block_destroy(self, x, y, z, value):
            if value == 3: # disables grenade damage
                return False
            if connection.on_block_destroy(self, x, y, z, value) == False:
                return False

        def on_block_build(self, x, y, z):
            self.refill()
            if connection.on_block_build(self, x, y, z) == False:
                return False

        def on_line_build(self, points):
            self.refill()
            if connection.on_line_build(self, points) == False:
                return False

        def on_hit(self, hit_amount, player, _type, grenade):
            if connection.on_hit(self, hit_amount, player, _type, grenade) == False:
                return False
            if self.team.id == 0:
                if player.team.id == 1:
                    return False
            if self.team.id == 1:
                return False

        def on_orientation_update(self, x, y, z):
            if self.info_mode:
                if self.world_object.cast_ray(128) != self.info_cur:
                    self.info_cur = self.world_object.cast_ray(128)
                    self.send_cmsg(str(self.info_cur) + ' #%02X%02X%02X ' % self.protocol.map.get_color(*self.info_cur) + str(self.protocol.map.get_color(*self.info_cur)), 'Notice')
            connection.on_orientation_update(self, x, y, z)

    class NoCaptureProtocol(protocol):

        def on_base_spawn(self, x, y, z, base, entity_id):
            return HIDE_POS

        def on_flag_spawn(self, x, y, z, flag, entity_id):
            return HIDE_POS

    return NoCaptureProtocol, NoCaptureConnection
