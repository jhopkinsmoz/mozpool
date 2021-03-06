# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sqlalchemy as sa

metadata = sa.MetaData()

devices = sa.Table('devices', metadata,
    sa.Column('id', sa.Integer(unsigned=True), primary_key=True, nullable=False),
    sa.Column('name', sa.String(32), unique=True, nullable=False),
    sa.Column('fqdn', sa.String(256), nullable=False),
    sa.Column('inventory_id', sa.Integer(unsigned=True), nullable=False),
    sa.Column('state', sa.String(32), nullable=False),
    sa.Column('state_counters', sa.Text, nullable=False),
    sa.Column('state_timeout', sa.DateTime, nullable=True),
    sa.Column('mac_address', sa.String(12), nullable=False),
    sa.Column('imaging_server_id', sa.Integer(unsigned=True),
        sa.ForeignKey('imaging_servers.id', ondelete='RESTRICT'),
        nullable=False),
    sa.Column('last_pxe_config_id', sa.Integer(unsigned=True),
        sa.ForeignKey('pxe_configs.id', ondelete='RESTRICT'),
        nullable=True),
    sa.Column('relay_info', sa.Text),
    sa.Column('boot_config', sa.Text),
)

requests = sa.Table('requests', metadata,
    # the schema specifies this as a BigInt; we use Integer here because it
    # seems that having the primary key as a BigInt doesn't work properly in
    # sqlite.
    sa.Column('id', sa.Integer(unsigned=True), primary_key=True, nullable=False),
    sa.Column('imaging_server_id', sa.Integer(unsigned=True),
        sa.ForeignKey('imaging_servers.id', ondelete='RESTRICT'),
        nullable=False),
    sa.Column('requested_device', sa.String(32), nullable=False),
    sa.Column('assignee', sa.String(256), nullable=False),
    sa.Column('expires', sa.DateTime, nullable=False),  # UTC
    sa.Column('boot_config', sa.Text),
    sa.Column('state', sa.String(32), nullable=False),
    sa.Column('state_counters', sa.Text, nullable=False),
    sa.Column('state_timeout', sa.DateTime, nullable=True),
)

device_requests = sa.Table('device_requests', metadata,
    sa.Column('request_id', sa.Integer(unsigned=True),
        sa.ForeignKey('requests.id', ondelete='RESTRICT'),
        unique=True, nullable=False),
    sa.Column('device_id', sa.Integer(unsigned=True),
        sa.ForeignKey('devices.id', ondelete='RESTRICT'),
        unique=True, nullable=False),
)

imaging_servers = sa.Table('imaging_servers', metadata,
    sa.Column('id', sa.Integer(unsigned=True), primary_key=True, nullable=False),
    sa.Column('fqdn', sa.String(256), nullable=False, unique=True),
)

pxe_configs = sa.Table('pxe_configs', metadata,
    sa.Column('id', sa.Integer(unsigned=True), primary_key=True, nullable=False),
    sa.Column('name', sa.String(32), unique=True, nullable=False),
    sa.Column('description', sa.Text, nullable=False),
    sa.Column('contents', sa.Text, nullable=False),
    sa.Column('active', sa.Boolean, nullable=False),
)

device_logs = sa.Table('device_logs', metadata,
    sa.Column('device_id', sa.Integer(unsigned=True), nullable=False),
    sa.Column('ts', sa.DateTime, nullable=False),
    sa.Column('source', sa.String(32), nullable=False),
    sa.Column('message', sa.Text, nullable=False),
)

request_logs = sa.Table('request_logs', metadata,
    sa.Column('request_id', sa.Integer(unsigned=True), nullable=False),
    sa.Column('ts', sa.DateTime, nullable=False),
    sa.Column('source', sa.String(32), nullable=False),
    sa.Column('message', sa.Text, nullable=False),
)
