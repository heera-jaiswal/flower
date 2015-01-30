from __future__ import absolute_import

import logging

from functools import partial
from pprint import pformat

from tornado import websocket
from tornado.ioloop import PeriodicCallback

from . import settings
from ..models import WorkersModel

from scheduler.core import load_action
from scheduler.settings import LOGDIR

logger = logging.getLogger(__name__)


class UpdateWorkers(websocket.WebSocketHandler):
    listeners = []
    periodic_callback = None
    workers = None

    def open(self):
        if not settings.AUTO_REFRESH:
            self.write_message({})
            return

        app = self.application

        if not self.listeners:
            logger.debug('Starting a timer for dashboard updates')
            periodic_callback = self.periodic_callback or PeriodicCallback(
                partial(UpdateWorkers.on_update_time, app),
                settings.PAGE_UPDATE_INTERVAL)
            if not periodic_callback._running:
                periodic_callback.start()
        self.listeners.append(self)

    def on_message(self, message):
        pass

    def on_close(self):
        if self in self.listeners:
            self.listeners.remove(self)
        if not self.listeners and self.periodic_callback:
            logger.debug('Stopping dashboard updates timer')
            self.periodic_callback.stop()

    @classmethod
    def on_update_time(cls, app):
        workers = WorkersModel.get_latest(app)
        changes = workers.workers

        if workers != cls.workers and changes:
            logger.debug('Sending dashboard updates: %s', pformat(changes))
            for l in cls.listeners:
                l.write_message(changes)
            cls.workers = workers

class UpdateTasks(websocket.WebSocketHandler):
    listeners = []
    periodic_callback = None
    tasks = None

    def open(self):
        if not settings.AUTO_REFRESH:
            self.write_message({})
            return

        app = self.application
        limit = self.get_argument('limit', default=None, type=int)
        worker = self.get_argument('worker', None)
        type = self.get_argument('type', None)
        state = self.get_argument('state', None)
        meta = self.get_argument('meta', None)

        worker = worker if worker != 'All' else None
        type = type if type != 'All' else None
        state = state if state != 'All' else None

        self.tasks = [task for task in TaskModel.iter_tasks(app, limit=limit, type=type,
                                               worker=worker, state=state)]


        if not self.listeners:
            logger.debug('Starting a timer for dashboard updates')
            periodic_callback = self.periodic_callback or PeriodicCallback(
                partial(UpdateTasks.on_update_time, app),
                settings.PAGE_UPDATE_INTERVAL)
            if not periodic_callback._running:
                periodic_callback.start()
        self.listeners.append(self)

    def on_message(self, message):
        pass

    def on_close(self):
        if self in self.listeners:
            self.listeners.remove(self)
        if not self.listeners and self.periodic_callback:
            logger.debug('Stopping dashboard updates timer')
            self.periodic_callback.stop()

    @classmethod
    def on_update_time(cls, app):
        tasks = [task for task in TaskModel.iter_tasks(app, limit=limit, 
                                                   type=type,
                                                   worker=worker, state=state)]

        if tasks != cls.tasks:
            print tasks
            

class UpdateLogfile(websocket.WebSocketHandler):
    listeners = []
    periodic_callback = None
    logfile = None

    def open(self):
        if not settings.AUTO_REFRESH:
            self.write_message({})
            return

        app = self.application

        if not self.listeners:
            logger.debug('Starting a timer for dashboard updates')
            periodic_callback = self.periodic_callback or PeriodicCallback(
                partial(UpdateLogfile.on_update_time, app),
                settings.PAGE_UPDATE_INTERVAL)
            if not periodic_callback._running:
                periodic_callback.start()
        self.listeners.append(self)

    def on_message(self, message):
        pass

    def on_close(self):
        if self in self.listeners:
            self.listeners.remove(self)
        if not self.listeners and self.periodic_callback:
            logger.debug('Stopping dashboard updates timer')
            self.periodic_callback.stop()

    @classmethod
    def on_update_time(cls, app):
        workers = WorkersModel.get_latest(app)
        changes = workers.workers

        if workers != cls.workers and changes:
            logger.debug('Sending dashboard updates: %s', pformat(changes))
            for l in cls.listeners:
                l.write_message(changes)
            cls.workers = workers
