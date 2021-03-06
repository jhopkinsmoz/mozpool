/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

var JobRunner = function () {
    this.initialize(arguments);
};

$.extend(JobRunner.prototype, {
    initialize: function(args) {
        this.collection = args[0];
        _.bindAll(this, 'maybeStartJob', 'jobFinished');
        this.running = null;

        window.job_queue.bind('add', this.maybeStartJob);
    },

    maybeStartJob: function() {
        if (this.running) {
            return;
        }

        if (window.job_queue.length == 0) {
            return;
        }

        // get the job, but don't unqueue it yet
        this.running = window.job_queue.at(0);

        // run the job
        console.log("running", this.running.get('job_type'), 'for', this.running.job_subject());

        var job_type = this.running.get('job_type');
        if (job_type == 'bmm-power-cycle') {
            this.runBmmPowerCycle();
        } else if (job_type == 'bmm-power-off') {
            this.runBmmPowerOff();
        } else if (job_type == 'lifeguard-power-cycle') {
            this.runLifeguardPowerCycle();
        } else if (job_type == 'lifeguard-pxe-boot') {
            this.runLifeguardPxeBoot();
        } else if (job_type == 'lifeguard-force-state') {
            this.runLifeguardForceState();
        } else if (job_type == 'mozpool-close-request') {
            this.runMozpoolCloseRequest();
        } else if (job_type == 'mozpool-renew-request') {
            this.runMozpoolRenewRequest();
        } else if (job_type == 'mozpool-create-request') {
            this.runMozpoolCreateRequest();
        } else {
            this.handleError('unknown job type ' + job_type);
            this.jobFinished();
        }
    },

    runBmmPowerCycle: function() {
        var self = this;

        var job_args = this.running.get('job_args');
        var url = '//' + this.running.get('device').get('imaging_server') + '/api/device/'
            + this.running.get('device_name') + '/power-cycle/';
        var post_params = {};
        if (job_args['pxe_config']) {
            post_params['pxe_config'] = job_args['pxe_config'];
            post_params['boot_config'] = JSON.stringify(job_args['boot_config']);
        }
        $.ajax(url, {
            type: 'POST',
            data: JSON.stringify(post_params),
            error: function (jqxhr, textStatus, errorThrown) {
                self.handleError('error from server: ' + textStatus + ' - ' + errorThrown);
            },
            complete: this.jobFinished
        });
    },

    runBmmPowerOff: function() {
        var self = this;

        var job_args = this.running.get('job_args');
        var url = '//' + this.running.get('device').get('imaging_server') + '/api/device/'
            + this.running.get('device_name') + '/power-off/';
        $.ajax(url, {
            type: 'GET',
            error: function (jqxhr, textStatus, errorThrown) {
                self.handleError('error from server: ' + textStatus + ' - ' + errorThrown);
            },
            complete: this.jobFinished
        });
    },

    runLifeguardPowerCycle: function() {
        var self = this;

        var job_args = this.running.get('job_args');
        var url = '//' + this.running.get('device').get('imaging_server') + '/api/device/'
            + this.running.get('device_name') + '/event/please_power_cycle/';
        $.ajax(url, {
            type: 'GET',
            error: function (jqxhr, textStatus, errorThrown) {
                self.handleError('error from server: ' + textStatus + ' - ' + errorThrown);
            },
            complete: this.jobFinished
        });
    },

    runLifeguardPxeBoot: function() {
        var self = this;

        var job_args = this.running.get('job_args');
        var url = '//' + this.running.get('device').get('imaging_server') + '/api/device/'
            + this.running.get('device_name') + '/event/please_pxe_boot/';
        var post_params = {};
        if (job_args['pxe_config']) {
            post_params['pxe_config'] = job_args['pxe_config'];
            post_params['boot_config'] = JSON.stringify(job_args['boot_config']);
        }
        $.ajax(url, {
            type: 'POST',
            data: JSON.stringify(post_params),
            error: function (jqxhr, textStatus, errorThrown) {
                self.handleError('error from server: ' + textStatus + ' - ' + errorThrown);
            },
            complete: this.jobFinished
        });
    },

    runLifeguardForceState: function() {
        var self = this;

        var job_args = this.running.get('job_args');
        var url = '//' + this.running.get('device').get('imaging_server') + '/api/device/'
            + this.running.get('device_name') + '/state-change/' + job_args.old_state + '/to/'
            + job_args.new_state + '/';
        var post_params = {};
        if (job_args['pxe_config']) {
            post_params['pxe_config'] = job_args['pxe_config'];
            post_params['boot_config'] = JSON.stringify(job_args['boot_config']);
        }
        $.ajax(url, {
            type: 'POST',
            data: JSON.stringify(post_params),
            error: function (jqxhr, textStatus, errorThrown) {
                self.handleError('error from server: ' + textStatus + ' - ' + errorThrown);
            },
            complete: this.jobFinished
        });
    },

    runMozpoolCloseRequest: function() {
        var self = this;

        var url = '//' + this.running.get('request').get('imaging_server') + '/api/request/' + this.running.get('request_id')  + '/return/';
        $.ajax(url, {
            type: 'POST',
            error: function (jqxhr, textStatus, errorThrown) {
                self.handleError('error from server: ' + textStatus + ' - ' + errorThrown);
            },
            complete: this.jobFinished
        });
    },

    runMozpoolRenewRequest: function() {
        var self = this;

        var url = '//' + this.running.get('request').get('imaging_server') + '/api/request/' + this.running.get('request_id')  + '/renew/';
        var job_args = this.running.get('job_args');
        var post_params = {duration: job_args['duration']};
        $.ajax(url, {
            type: 'POST',
            data: JSON.stringify(post_params),
            error: function (jqxhr, textStatus, errorThrown) {
                self.handleError('error from server: ' + textStatus + ' - ' + errorThrown);
            },
            complete: this.jobFinished
        });
    },

    runMozpoolCreateRequest: function() {
        var self = this;

        var job_args = this.running.get('job_args');
        var url = '/api/device/' + job_args.device  + '/request/';
        var post_params = {
            duration: job_args.duration,
            assignee: job_args.assignee
        };
        if (job_args.b2gbase) {
            post_params.boot_config = {
                version: 1,
                b2gbase: job_args.b2gbase
            };
        }
        
        $.ajax(url, {
            type: 'POST',
            data: JSON.stringify(post_params),
            error: function (jqxhr, textStatus, errorThrown) {
                self.handleError('error from server: ' + textStatus + ' - ' + errorThrown);
            },
            complete: this.jobFinished
        });
    },

    jobFinished: function() {
        var self = this;
        this.running = null;
        window.job_queue.shift();
        this.collection.update();
        _.defer(function() { self.maybeStartJob(); });
    },

    handleError: function(msg) {
        console.log(msg);
        if (!this.alreadyAlerted) {
            this.alreadyAlerted = true;
            alert("Errors from the server; see the console log (cmd-opt-k)");
        }
    }
});
