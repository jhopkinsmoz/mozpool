Overview
========

For an overview of what Mozpool is and how it's used at Mozilla, see

  https://wiki.mozilla.org/ReleaseEngineering/Mozpool

Comprehensive, High-Level Design Description
============================================

MozPool is a tool for managing a pool of untrustworthy mobile devices.  It is
deployed as a single system, but comprised of several distinct components for
design simplicity.

Component Design
----------------

## MozPool ##

It shouldn't cause too much confusion that the top-level component is also
known as MozPool.  It's just such a great name.

MozPool is responsible for matching *requests* with *devices*.  A new request is
submitted by a client with parameters for acceptable devices (may be as broad as
"anything" or as narrow as "this panda" and the expected condition of that
device (Android suitable for Fennec, or a particular B2G image, or booted to the
live image for diagnostic purposes).  Clients can be automated test systems
(Buildbot, Autophone) or flesh-and-blood users.

Requests are filled by matching them with a single device.  Once that match is
made and returned to the client, the request stays around as a form of
reservation.  Reservations time out if they are not renewed periodically, where
the period is specified by the client (so flesh-and-blood users can reserve a
device for a day or two, while automated systems can use 30 minutes or something
smaller).

When matching a request to a device, MozPool picks a device itself, but relies on
LifeGuard to keep information about the available devices up to date, and to put
the requested device in the desired state.  If LifeGuard fails to set up the
device as desired, MozPool is responsible for picking another device that
satisfies the request, or indicating failure to the client, if the parameters
of the request cannot be satisfied.

MozPool also provides various statistics and reports as needed to maintain the
health of the pool.  These include summaries of the status of devices by type
(where status is divided into simple categories like "in use", "idle",
"processing", and "failed"); and lists of devices in known failure states
requiring human remediation.

In the initial design, MozPool is entirely reactive, but the design does not
preclude predictive or proactive operations, e.g., balancing the distribution
of images on spare devices, predictively installing B2G images, etc.

## LifeGuard ##

LifeGuard deals only with devices.  It actively tracks the state of every
device, and handles requests from MozPool to change the state of a device, via
events.  These events ask the device to "please" perform some action.  If the
device is not in the expected state, the request is ignored.

Most states for a device involve periodic checks from LifeGuard.

## BMM ##

BMM, short for Black Mobile Magic, is the lowest-level component, and handles
technical operations on devices as requested from LifeGuard.  The available
operations are power-cycling a device; PXE-booting a device; pinging a device;
and running commands on a device via SUTAgent.  BMM includes TFTP and HTTP
services to allow a device to be booted into a Linux live-boot environment, and
scripts run there to perform whatever actions are appropriate.

Specific scripts implement actions required by LifeGuard: install Android,
install a B2G image, run an SSH server in maintenance mode, run system checks,
etc.  Each of these have corresponding states in the Lifeguard state machine.

BMM abstracts away the details of how power is controlled for each device, as
well as the particulars of boot images for specific hardware.

Other Features
--------------

## Logging ##

As much logging as possible is funneled through syslog and into the mysql
database, to help with debugging.

Logs are expired after some time by the database itself (see `sql/schema.sql`).

## Inventory Sync ##

The Mozilla inventory (https://inventory.mozilla.org) is the source of truth
from which the list of devices is derived.  The database is automatically
synchronized with inventory periodically.

Implementation
--------------

## Hosting ##

Each device is assigned, in inventory, to a specific mobile-imaging server.  In
general, that server is "close" to the device, physically or virtually.

All three major components are implemented in the same Python daemon, running
web services based on web.py.  An instance of this daemon runs on each
mobile-imaging server.

The daemon runs background processes in separate threads.  In particular,
various operations poll for status.

There is no front-end load balancer.  If an imaging server is down or
unavailable, the devices assigned to it are also unavailable, but other devices
continue to be accessible.

## API Client ##

Clients access MozPool using an HTTP API.  The endpoint for that API is any
mobile-imaging server, since all are configured identically.  Clients should be
pre-configured with a list of servers, and retry servers in random order until
successful.

## Requests ##

The entire lifetime of each request is handled by MozPool as a formal state
machine.  The state is stored in the database. 

All state transitions and actions are handled on the server where the request
was originally made.  Timeouts are handled by polling the database for requests
with timeout timestamps in the past (using threads within the daemon).

If an imaging server is lost, the requests it manages become invalid when their
refresh interval expires.

Boards are claimed by inserting into a correspondance table in the database,
with constraints such that only one request can claim a device.

## Devices ##

Like requests, devices are managed by LifeGuard as a formal state machine.
MozPool has read-only visibility to device states for purposes of selecting
devices for requests, but uses conditional requests to LifeGuard to cause state
transitions (the intent being that MozPool will observe that a device is in the
idle state, claim it, then ask that LifeGuard transition it from idle to
rebooting; if the device has failed in the interim, LifeGuard will refuse to do
so).

All state transitions and actions are handled on the server to which the device
is assigned.

## Inter-Component Communication ##

MozPool communicates with LifeGuard using an HTTP API, selecting the endpoint
based on the assigned imaging server in the database. This may result in a
MozPool server contacting itself via HTTP.

LifeGuard communicates with BMM using regular old Python function invocations.

Usage
=====

Configuration
-------------

Configuration should be based on the mozpool/config.ini.dist template.  The
config can either be put in the `mozpool/config.ini`, or anywhere else with
`$MOZPOOL_CONFIG` giving the full path.

Server
------

To run the server daemon:

    mozpool-server

optionally, add a port on the command line for the HTTP server:

    mozpool-server 8010

Database
--------

To install the DB schema (using the configured database):

    mozpool-db create-schema

And to install test adta

    mozpool-db run testdata.py

Relays
------

To control relays:

    relay powercycle <hostname> <bank> <relay>
    relay status <hostname> <bank> <relay>
    relay turnon <hostname> <bank> <relay>
    relay turnoff <hostname> <bank> <relay>

Note: do not manually adjust relays that are also under MozPool's active control!

PXE Configs
-----------

PXE configurations can be edited with the `pxe-config` command.  See its help
for more information:

    pxe-config --help

Inventory Sync
--------------

To synchronize the internal DB with inventory:

    mozpool-inventorysync

(use `--verbose` to see what it's up to - note that it's not too fast!)

Tests
-----

To run the tests:

 * install mock
 * install paste
 * run `python runtests.py`
