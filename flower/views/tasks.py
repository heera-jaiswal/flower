from __future__ import absolute_import

import sys
import copy
import logging
import ast

try:
    from itertools import imap
except ImportError:
    imap = map

from tornado import web

from ..views import BaseHandler
from ..utils.tasks import iter_tasks, get_task_by_id, as_dict
from ..utils.actions import get_action_conf, get_logfile

logger = logging.getLogger(__name__)


class TaskView(BaseHandler):
    @web.authenticated
    def get(self, task_id):
        task = get_task_by_id(self.application.events, task_id)

        capp = self.application.capp
        if capp.conf.CELERY_TIMEZONE:
            tz = capp.conf.CELERY_TIMEZONE
        else:
            tz = 'UTC'

        if task is None:
            raise web.HTTPError(404, "Unknown task '%s'" % task_id)

        if task.action_id:
            logfile, logpath = get_logfile('actions', task.action_id)
        elif task.workflow:
            logfile, logpath = get_logfile('cycles', 'cycle_%s' % task.cycle_dt)
        else:
            logfile, logpath = None, None

        action_conf = get_action_conf(task.template or task.action_id) if task.action_id else None
    
        self.render("task.html", task=task,
                                 action_conf=action_conf,
                                 logfile=logfile,
                                 logpath=logpath,
                                 cycle_dt=task.cycle_dt,
                                 tz=tz)


class TasksDataTable(BaseHandler):
    @web.authenticated
    def get(self):
        app = self.application
        draw = self.get_argument('draw', type=int)
        start = self.get_argument('start', type=int)
        length = self.get_argument('length', type=int)
        search = self.get_argument('search[value]', type=str)

        column = self.get_argument('order[0][column]', type=int)
        sort_by = self.get_argument('columns[%s][data]' % column, type=str)
        sort_order = self.get_argument('order[0][dir]', type=str) == 'asc'

        def key(item):
            val = getattr(item[1], sort_by)
            if sys.version_info[0] == 3:
                val = str(val)
            return val

        tasks = sorted(iter_tasks(app.events, search=search),
                       key=key, reverse=sort_order)
        tasks = list(map(self.format_task, tasks))
        filtered_tasks = []
        i = 0
        for _, task in tasks:
            if i < start:
                i += 1
                continue
            if i >= (start + length):
                break
            task = as_dict(task)

            if task['worker']:
                task['worker'] = task['worker'].hostname
            filtered_tasks.append(task)
            i += 1

        self.write(dict(draw=draw, data=filtered_tasks,
                        recordsTotal=len(tasks),
                        recordsFiltered=len(tasks)))

    def format_task(self, args):
        uuid, task = args
        custom_format_task = self.application.options.format_task

        if custom_format_task:
            task = custom_format_task(copy.copy(task))
        return uuid, task


class TasksView(BaseHandler):
    @web.authenticated
    def get(self):
        app = self.application
        capp = self.application.capp

        time = 'natural-time' if app.options.natural_time else 'time'
        if capp.conf.CELERY_TIMEZONE:
            time += '-' + capp.conf.CELERY_TIMEZONE

        self.render(
            "tasks.html",
            tasks=[],
            columns=app.options.tasks_columns,
            time=time,
        )
