# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import sqlalchemy
from sqlalchemy.sql import exists, not_, or_, select
from itertools import izip_longest
from mozpool.db import logs, model, sql
from mozpool import config

class NotFound(Exception):
    pass

class InvalidStateChange(Exception):
    
    def __init__(self, old_state, new_state, current_state):
        self.old_state = old_state
        self.new_state = new_state
        self.current_state = current_state
        Exception.__init__(self, 'invalid state change request from "%s" '
                           'to "%s" in current state "%s"' %
                           (self.old_state, self.new_state, self.current_state))

def row_to_dict(row, table, omit_cols=[]):
    """
    Convert a result row to a dict using the schema from table.
    If omit_cols is specified, omit columns whose names are present
    in that list.
    """
    result = {}
    for col in table.c:
        if col.name in omit_cols:
            continue
        coldata = row[col]
        if isinstance(coldata, unicode):
            coldata = coldata.encode('utf-8')
        result[col.name] = coldata
    return result

def list_devices():
    """
    Get the list of all devices known to the system.
    Returns a dict whose 'devices' entry is the list of devices.
    """
    conn = sql.get_conn()
    res = conn.execute(select([model.devices.c.name]))
    return {'devices': [row[0].encode('utf-8') for row in res]}

def dump_devices(*device_names):
    """
    Dump device data.  This returns a list of dictionaries with keys id, name,
    fqdn, invenetory_id, mac_address, imaging_server, relay_info, and state.
    Zero or more device names should be passed in as positional arguments.  If
    none are given, dumps all device data.
    """
    conn = sql.get_conn()
    devices = model.devices
    img_svrs = model.imaging_servers
    stmt = sqlalchemy.select(
        [devices.c.id, devices.c.name, devices.c.fqdn, devices.c.inventory_id,
         devices.c.mac_address, img_svrs.c.fqdn.label('imaging_server'),
         devices.c.relay_info, devices.c.state],
        from_obj=[devices.join(img_svrs)])
    if device_names:
        id_exprs = []
        for i in device_names:
            id_exprs.append('devices.name=="%s"' % i)
        if len(id_exprs) == 1:
            id_exprs = id_exprs[0]
        else:
            id_exprs = or_(*id_exprs)
        stmt = stmt.where(id_exprs)
    res = conn.execute(stmt)
    return [dict(row) for row in res]

def find_imaging_server_id(name):
    """Given an imaging server name, either return the existing ID, or a new ID."""
    conn = sql.get_conn()

    # try inserting, ignoring failures (most likely due to duplicate row)
    try:
        conn.execute(model.imaging_servers.insert(),
            fqdn=name)
    except sqlalchemy.exc.SQLAlchemyError:
        pass # probably already exists

    res = conn.execute(sqlalchemy.select([ model.imaging_servers.c.id ],
                        whereclause=(model.imaging_servers.c.fqdn==name)))
    return res.fetchall()[0].id

def insert_device(values):
    """Insert a new device into the DB.  VALUES should be in the dictionary
    format used for inventorysync - see inventorysync.py"""
    values = values.copy()

    # convert imaging_server to its ID, and add a default state and counters
    values['imaging_server_id'] = find_imaging_server_id(values.pop('imaging_server'))
    values['state'] = 'new'
    values['state_counters'] = '{}'

    sql.get_conn().execute(model.devices.insert(), [ values ])

def delete_device(id):
    """Delete the device with the given ID"""
    conn = sql.get_conn()
    # foreign keys don't automatically delete log entries, so do it manually.
    # This table is partitioned, so there's no need to later optimize these
    # deletes - they'll get flushed when their parititon is dropped.
    logs.device_logs.delete_all(id)
    conn.execute(model.devices.delete(), whereclause=(model.devices.c.id==id))

def update_device(id, values):
    """Update an existing device with id ID into the DB.  VALUES should be in
    the dictionary format used for inventorysync - see inventorysync.py"""
    values = values.copy()

    # convert imaging_server to its ID, and strip the id
    values['imaging_server_id'] = find_imaging_server_id(values.pop('imaging_server'))
    if 'id' in values:
        values.pop('id')

    sql.get_conn().execute(model.devices.update(whereclause=(model.devices.c.id==id)), **values)

def get_server_for_device(device):
    """
    Get the name of the imaging server associated with this device.
    """
    res = sql.get_conn().execute(select([model.imaging_servers.c.fqdn],
                                        from_obj=[model.devices.join(model.imaging_servers)]).where(model.devices.c.name == device))
    row = res.fetchone()
    if row is None:
        raise NotFound
    return row[0].encode('utf-8')

# state machine utilities

def get_state(tbl, id_col, id_val):
    """
    Get the state of this object - (state, timeout, counters)
    """
    res = sql.get_conn().execute(select(
        [tbl.c.state, tbl.c.state_timeout, tbl.c.state_counters],
        id_col==id_val))
    row = res.fetchone()
    if row is None:
        raise NotFound
    state_counters = row['state_counters']
    if state_counters:
        state_counters = json.loads(state_counters)
    else:
        state_counters = {}
    return row['state'], row['state_timeout'], state_counters

def set_state(tbl, id_col, id_val, state, timeout):
    """
    Set the state of this object, without counters
    """
    sql.get_conn().execute(tbl.update().
                           where(id_col==id_val).
                           values(state=state, state_timeout=timeout))

def set_counters(tbl, id_col, id_val, counters):
    """
    Set the counters for this object
    """
    sql.get_conn().execute(tbl.update().
                           where(id_col==id_val).
                           values(state_counters=json.dumps(counters)))

def get_timed_out(tbl, id_col, imaging_server_id):
    """
    Get a list of all devices whose timeout is in the past, and which belong to
    this imaging server.
    """
    now = datetime.datetime.now()
    res = sql.get_conn().execute(select(
            [id_col],
            (tbl.c.state_timeout < now)
            & (tbl.c.imaging_server_id == imaging_server_id)))
    timed_out = [r[0] for r in res.fetchall()]
    return timed_out


# device state utilities

def get_device_state(device_name):
    return get_state(model.devices, model.devices.c.name, device_name)

def set_device_state(device_name, state, timeout):
    return set_state(model.devices, model.devices.c.name, device_name, state,
                     timeout)

def set_device_counters(device_name, counters):
    return set_counters(model.devices, model.devices.c.name, device_name,
                        counters)

def get_timed_out_devices(imaging_server_id):
    return get_timed_out(model.devices, model.devices.c.name, imaging_server_id)

def object_status(tbl, id_col, id_val, logs_obj):
    """
    Get the status of device.
    """
    res = sql.get_conn().execute(select([tbl.c.state],
                                        id_col==id_val))
    row = res.fetchall()[0]
    return {"state": row['state'].encode('utf-8'),
            "log": logs_obj.get(id_val)}


# The rest of the device methods should not have to check for a valid device.
# Handler methods will check before calling.
def device_status(device):
    return object_status(model.devices, model.devices.c.name, device,
                         logs.device_logs)

def device_config(device):
    """
    Get the boot config and last pxe_config for this device.
    """
    res = sql.get_conn().execute(select(
        [model.devices.c.boot_config, model.pxe_configs.c.name],
        from_obj=model.devices.outerjoin(model.pxe_configs,
                model.devices.c.last_pxe_config_id==model.pxe_configs.c.id),
        whereclause=(model.devices.c.name==device)))
    row = res.fetchone()
    if row:
        return {'boot_config': row['boot_config'], 'pxe_config': row['name']}
    else:
        return {}

def set_device_config(device, pxe_config_name, boot_config):
    """
    Set the config parameters for the /boot/ API for device.
    """
    assert isinstance(boot_config, (str, unicode))
    conn = sql.get_conn()
    res = conn.execute(select([model.pxe_configs.c.id]).
            where(model.pxe_configs.c.name==pxe_config_name))
    pxe_config_id = res.fetchall()[0][0]
    conn.execute(model.devices.update().
                 where(model.devices.c.name==device).
                 values(last_pxe_config_id=pxe_config_id,
                         boot_config=boot_config))
    return config

def device_relay_info(device):
    res = sql.get_conn().execute(select([model.devices.c.relay_info],
                                        model.devices.c.name==device))
    row = res.fetchone()
    if not row:
        raise NotFound
    hostname, bank, relay = row[0].split(":", 2)
    assert bank.startswith("bank") and relay.startswith("relay")
    return hostname, int(bank[4:]), int(relay[5:])

def mac_with_dashes(mac):
    """
    Reformat a 12-digit MAC address to contain
    a dash between each 2 characters.
    """
    # From the itertools docs.
    return "-".join("%s%s" % i for i in izip_longest(fillvalue=None, *[iter(mac)]*2))

def device_mac_address(device):
    """
    Get the mac address of device.
    """
    res = sql.get_conn().execute(select([model.devices.c.mac_address],
                                        model.devices.c.name==device))
    row = res.fetchone()
    return row['mac_address'].encode('utf-8')

def device_fqdn(device):
    """
    Get the fqdn of device.
    """
    res = sql.get_conn().execute(select([model.devices.c.fqdn],
                                        model.devices.c.name==device))
    row = res.fetchone()
    return row['fqdn']

def list_pxe_configs(active_only=False):
    conn = sql.get_conn()
    q = select([model.pxe_configs.c.name])
    if active_only:
        q = q.where(model.pxe_configs.c.active)
    res = conn.execute(q)
    return {'pxe_configs': [row[0].encode('utf-8') for row in res]}

def pxe_config_details(name):
    conn = sql.get_conn()
    res = conn.execute(select([model.pxe_configs],
                              model.pxe_configs.c.name==name))
    row = res.fetchone()
    if row is None:
        raise NotFound
    return {'details': row_to_dict(row, model.pxe_configs, omit_cols=['id'])}

def add_pxe_config(name, description, active, contents):
    sql.get_conn().execute(model.pxe_configs.insert(),
            [ {'name':name, 'description':description, 'active':active, 'contents':contents} ])

def update_pxe_config(name, description=None, active=None, contents=None):
    updates = {}
    if description:
        updates['description'] = description
    if active is not None:
        updates['active'] = active
    if contents is not None:
        updates['contents'] = contents
    sql.get_conn().execute(model.pxe_configs.update(
                    model.pxe_configs.c.name == name),
                **updates)

# request utilities

def get_request_state(request_id):
    return get_state(model.requests, model.requests.c.id, request_id)

def set_request_state(request_id, state, timeout):
    return set_state(model.requests, model.requests.c.id, request_id, state,
                     timeout)

def set_request_counters(request_id, counters):
    return set_counters(model.requests, model.requests.c.id, request_id,
                        counters)

def get_timed_out_requests(imaging_server_id):
    return get_timed_out(model.requests, model.requests.c.id, imaging_server_id)

def request_status(request_id):
    return object_status(model.requests, model.requests.c.id, request_id,
                         logs.request_logs)

def get_free_devices():
    # FIXME: prefer devices that already have the requested boot_config
    # installed.
    conn = sql.get_conn()
    res = conn.execute(select([model.devices.c.name],
                              model.devices.c.state=="free").where(
            not_(exists(select([model.device_requests.c.request_id]).where(
                        model.device_requests.c.device_id==model.devices.c.id)))
            ))
    return [row[0] for row in res]

def create_request(requested_device, assignee, duration, boot_config):
    conn = sql.get_conn()
    server_id = conn.execute(select(
            [model.imaging_servers.c.id],
            model.imaging_servers.c.fqdn==config.get('server', 'fqdn'))
                             ).fetchall()[0][0]
    reservation = {'imaging_server_id': server_id,
                   'requested_device': requested_device,
                   'assignee': assignee,
                   'expires': datetime.datetime.utcnow() +
                              datetime.timedelta(seconds=duration),
                   'boot_config': json.dumps(boot_config),
                   'state': 'new',
                   'state_counters': '{}'}

    res = conn.execute(model.requests.insert(), reservation)
    return res.lastrowid

def reserve_device(request_id, device_name):
    conn = sql.get_conn()
    device_id = conn.execute(select(
            [model.devices.c.id],
            model.devices.c.name==device_name)).fetchone()[0]
    if not device_id:
        raise NotFound
    try:
        conn.execute(model.device_requests.insert(),
                     {'request_id': request_id, 'device_id': device_id})
    except sqlalchemy.exc.IntegrityError:
        return False
    return True

def get_server_for_request(request_id):
    """
    Get the name of the imaging server associated with this device.
    """
    res = sql.get_conn().execute(select([model.imaging_servers.c.fqdn],
                                        from_obj=[model.requests.join(model.imaging_servers)]).where(model.requests.c.id == request_id))
    row = res.fetchone()
    if row is None:
        raise NotFound
    return row[0].encode('utf-8')

def all_imaging_servers():
    """
    Return a list of the fqdn's of all imaging servers
    """
    res = sql.get_conn().execute(select([model.imaging_servers.c.fqdn]))
    return [ row['fqdn'] for row in res.fetchall() ]

def clear_device_request(request_id):
    conn = sql.get_conn()
    conn.execute(model.device_requests.delete().where(
            model.device_requests.c.request_id==request_id))

def get_assigned_device(request_id):
    conn = sql.get_conn()
    res = conn.execute(select(
            [model.devices.c.name],
            from_obj=[model.device_requests.join(model.devices)]).where(
            model.device_requests.c.request_id==request_id))
    row = res.fetchone()
    if row:
        return row[0].encode('utf-8')
    return None

def get_request_for_device(device_name):
    conn = sql.get_conn()
    res = conn.execute(select(
            [model.device_requests.c.request_id],
            from_obj=[model.device_requests.join(model.devices)]).where(
            model.devices.c.name==device_name))
    row = res.fetchone()
    if row:
        return row[0]
    return None

def request_config(request_id):
    conn = sql.get_conn()
    res = conn.execute(select([model.requests.c.requested_device,
                               model.requests.c.assignee,
                               model.requests.c.expires,
                               model.requests.c.boot_config],
                              model.requests.c.id==request_id))
    row = res.fetchone()
    if row is None:
        raise NotFound

    request = {'id': request_id,
              'requested_device': row[0].encode('utf-8'),
              'assignee': row[1].encode('utf-8'),
              'expires': row[2].isoformat(),
              'boot_config': row[3].encode('utf-8'),
              'assigned_device': '',
              'url': 'http://%s/api/request/%d/' %
                (config.get('server', 'fqdn'), request_id)}

    assigned_device = get_assigned_device(request_id)
    if assigned_device:
        request['assigned_device'] = assigned_device
    return request

def dump_requests(*request_ids, **kwargs):
    conn = sql.get_conn()
    requests = model.requests
    stmt = sqlalchemy.select(
        [requests.c.id,
         model.imaging_servers.c.fqdn.label('imaging_server'),
         requests.c.assignee, requests.c.boot_config, requests.c.state,
         requests.c.expires, requests.c.requested_device],
        from_obj=[requests.join(model.imaging_servers)])
    if request_ids:
        id_exprs = []
        for i in request_ids:
            id_exprs.append('requests.id=%d' % i)
        if len(id_exprs) == 1:
            id_exprs = id_exprs[0]
        else:
            id_exprs = or_(*id_exprs)
        stmt = stmt.where(id_exprs)
    if not kwargs.get('include_closed', False):
        stmt = stmt.where(requests.c.state!='closed')
    res = conn.execute(stmt)
    requests = [dict(row) for row in res]
    res = conn.execute(sqlalchemy.select([model.device_requests.c.request_id,
                                          model.devices.c.name,
                                          model.devices.c.state],
                                         from_obj=[model.device_requests.join(model.devices)]))
    device_requests = dict([(x[0], (x[1], x[2])) for x in res])
    for r in requests:
        if r['id'] in device_requests:
            r['assigned_device'] = device_requests[r['id']][0]
            r['device_state'] = device_requests[r['id']][1]
        else:
            r['assigned_device'] = ''
            r['device_state'] = ''
    return requests

def renew_request(request_id, duration):
    conn = sql.get_conn()
    conn.execute(model.requests.update(model.requests).values(expires=datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)).where(model.requests.c.id==request_id))

def get_expired_requests(imaging_server_id):
    """
    Get a list of all requests whose 'expires' timestamp is in the past, are
    not in the 'expired' state, and which belong to this imaging server.
    """
    now = datetime.datetime.utcnow()
    res = sql.get_conn().execute(select(
            [model.requests.c.id],
            (model.requests.c.expires < now)
            & (model.requests.c.state != 'expired')
            & (model.requests.c.state != 'closed')
            & (model.requests.c.imaging_server_id == imaging_server_id)))
    expired = [r[0] for r in res.fetchall()]
    return expired
