from __future__ import absolute_import
from __future__ import with_statement

import ast
import os
import tailer

from celery.events.state import Task as _Task

from scheduler.core import discover_actions
from scheduler.settings import LOGDIR

try:
    from collections import OrderedDict
except ImportError:
    # celery <3.2 provides this
    from celery.utils.compat import OrderedDict


class BaseModel(object):
    def __init__(self, app):
        self.app = app

    def __eq__(self, other):
        raise NotImplementedError

    def __ne__(self, other):
        return not self.__eq__(other)


class WorkersModel(BaseModel):
    def __init__(self, app):
        super(WorkersModel, self).__init__(app)
        self.workers = OrderedDict()

        state = self.app.state
        for workername, stat in sorted(state.stats.items()):
            pool = stat.get('pool') or {}
            self.workers[workername] = dict(
                status=(workername in state.ping),
                concurrency=pool.get('max-concurrency'),
                completed_tasks=sum(stat.get('total', {}).values()),
                running_tasks=len(state.active_tasks.get(workername, [])),
                queues=[x['name'] for x in
                        state.active_queues.get(workername, []) if x]
            )

    @classmethod
    def get_latest(cls, app):
        workers = WorkersModel(app)
        for name, info in workers.workers.items():
            if 'dedicated' in name and not info['status']:
                workers.workers.pop(name)
        return workers

    @classmethod
    def get_workers(cls, app):
        return list(app.state.stats.keys())

    @classmethod
    def is_worker(cls, app, workername):
        return WorkerModel.get_worker(app, workername) is not None

    def __eq__(self, other):
        return other is not None and self.workers == other.workers


class WorkerModel(BaseModel):
    def __init__(self, app, name):
        super(WorkerModel, self).__init__(app)

        state = self.app.state
        self.name = name
        self.stats = state.stats[name]
        self.active_tasks = state.active_tasks.get(name, {})
        self.scheduled_tasks = state.scheduled_tasks.get(name, {})
        self.active_queues = state.active_queues.get(name, {})
        self.revoked_tasks = state.revoked_tasks.get(name, [])
        self.registered_tasks = [x for x in state.registered_tasks.get(
                                 name, {}) if not x.startswith('celery.')]
        self.reserved_tasks = state.reserved_tasks.get(name, {})
        self.conf = state.conf.get(name, {})

    @classmethod
    def get_worker(self, app, name):
        if name not in app.state.stats:
            return None
        return WorkerModel(app, name)

    def __eq__(self, other):
        return self.name == other.name and self.stats == other.stats and\
            self.active_tasks == other.active_tasks and\
            self.active_queues == other.active_queues and\
            self.revoked_tasks == other.revoked_tasks and\
            self.registered_tasks == other.registered_tasks and\
            self.scheduled_tasks == other.scheduled_tasks and\
            self.reserved_tasks == other.reserved_tasks and\
            self.conf == other.conf


class TaskModel(BaseModel):
    def __init__(self, app, task_id):
        self.uuid = task_id

    if hasattr(_Task, '_fields'):  # Old version
        @classmethod
        def get_task_by_id(cls, app, task_id):
            return app.events.state.tasks.get(task_id)
    else:
        _fields = _Task._defaults.keys()

        @classmethod
        def get_task_by_id(cls, app, task_id):
            task = app.events.state.tasks.get(task_id)
            if task is not None:
                task._fields = cls._fields
            return task

    @classmethod
    def iter_tasks(cls, app, limit=None, type=None, worker=None, state=None,
                   action_type=None, actions=None, cycles=[]):
        i = 0
        events_state = app.events.state
        for uuid, task in events_state.tasks_by_timestamp():
    
            if (isinstance(type, str) and task.name != type) or \
               (isinstance(type, list) and task.name not in type):
                continue

            if worker and task.worker and task.worker.hostname != worker:
                continue

            if state and task.state not in state:
                continue

            task.kwargs = ast.literal_eval(str(task.kwargs))

            if cycles and task.kwargs.has_key('cycle_dt')\
            and task.kwargs['cycle_dt'] not in cycles:
                continue

            if (actions != None and task.kwargs and\
                task.kwargs.has_key('action_id') and \
                task.kwargs['action_id'] not in actions) or\
                (actions != None and task.kwargs and not\
                 task.kwargs.has_key('action_id')):
                continue

            if action_type and task.kwargs.has_key('action_id')\
            and action_type not in task.kwargs['action_id']:
                continue

            yield uuid, task
            i += 1
            if i == limit:
                break

    @classmethod
    def seen_task_types(cls, app):
        return app.events.state.task_types()

    def __dir__(self):
        return self._fields

class CycleModel(BaseModel):

    @classmethod
    def get_log_file(cls, cycle_dt):
        logdir = os.path.join(LOGDIR, 'cycles')
        logpath = os.path.join(logdir, 'cycle_%s.log' % cycle_dt)
        if os.path.exists(logpath):
            with open(logpath) as log:
                logfile = os.linesep.join(tailer.tail(log, 500))
        else:
            logfile = None
            logpath = None
        return logfile, logpath

class ActionModel(BaseModel):
    def __init__(self, action_id):
        self.action_id = action_id

    @classmethod
    def get_action_conf(cls, action_id):
        actions = discover_actions()
        if actions.has_key(action_id):
            with open(actions[action_id]) as conf:
                action_conf = conf.read()
        else:
            action_conf = None
        
        return action_conf

    @classmethod
    def get_log_file(cls, action_id):
        logdir = os.path.join(LOGDIR, 'actions')
        logpath = os.path.join(logdir, '%s.log' % action_id)
        if os.path.exists(logpath):
            with open(logpath) as log:
                logfile = os.linesep.join(tailer.tail(log, 500))
        else:
            logfile = None
            logpath = None
        return logfile, logpath

class BrokerModel(BaseModel):
    def __init__(self, app):
        super(BrokerModel, self).__init__(app)

    @property
    def url(self):
        return self.app.celery_app.connection().as_uri()

    @property
    def queues(self):
        return self.app.state.broker_queues

    @property
    def info_available(self):
        if self.app.celery_app.connection().transport == 'amqp' and\
                not self.app.options.broker_api:
            return False
        return True
