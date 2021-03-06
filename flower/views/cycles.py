from __future__ import absolute_import

import copy
import logging
import ast
from operator import itemgetter

try:
    from itertools import imap
except ImportError:
    imap = map

from tornado import web

from ..views import BaseHandler
from ..utils.tasks import iter_tasks, get_task_by_id, as_dict
from .tasks import TasksDataTable

logger = logging.getLogger(__name__)



class CyclesView(BaseHandler):
    @web.authenticated
    def get(self):
        app = self.application
        capp = self.application.capp

        time = 'natural-time' if app.options.natural_time else 'time'
        if capp.conf.CELERY_TIMEZONE:
            time += '-' + capp.conf.CELERY_TIMEZONE
        columns = 'action_id,cycle_dt,state,received,eta,started,timestamp,runtime,worker,routing_key,retries,expires'
        tasks = sorted(iter_tasks(app.events, type='cycle.CycleTask'))
        cycle_tasks = []
        cycles = []
        for uuid, task in tasks:
            cycle = task.cycle_dt
            if cycle != None and cycle not in cycles:
                cycles.append(cycle)
                cycle_tasks.append((uuid,task))

        cycles.sort(reverse=True)
        tasks.sort(key=lambda x: x[1].cycle_dt, reverse=True)
        cycles.insert(0, 'All previous cycles')
        cycles.insert(0, 'All active cycles')
        cycles.insert(0, 'All cycles')
        self.render(
            "cycles.html",
            tasks=[],
            columns=columns,
            cycles_dt = cycles,
            cycle_tasks = cycle_tasks,
            cycle_dt=cycles[0] if cycles else '',
            time=time,
        )

class CyclesDataTable(BaseHandler):

    def _get_cycles(self, state):
        tasks = sorted(iter_tasks(self.application.events, type='cycle.CycleTask'))
        cycles = []
        for uuid, task in tasks:
            kwargs = ast.literal_eval(str(getattr(task, 'kwargs', {}))) or {}
            cycle_dt = kwargs.get('cycle_dt')
            if 'active' in state and task.state in ['STARTED', 'RUNNING']:
                cycles.append(cycle_dt)
            elif 'previous' in state and task.state not in ['STARTED','RUNNING']:
                cycles.append(cycle_dt)
            elif 'All cycles' in state: 
                cycles.append(cycle_dt)
        return cycles

    def _squash_allocation(self, tasks):
        # Get tasks allocating and 
        filter_tasks = []
        alloc_actions = []
        for task in tasks:
            if task['name'] == 'chain.AllocateChainTask':
                alloc_actions.append(task['action_id'])
            if task['name'] == 'chain.AllocateChainTask' and task['state'] in ['STARTED', 'RUNNING', 'SUCCESS']:
                continue
            else:
                filter_tasks.append(task)
        for task in filter_tasks:
            if task['name'] and 'tasks.' in task['name'] \
            and task['action_id'] in alloc_actions \
            and task['state'] in ['FAILURE']:
                filter_tasks.remove(task)
        return filter_tasks

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
        cycle_dt = self.get_argument('cycle_dt', type=str)

        if not cycle_dt:
            self.write(dict(draw=draw, data=[],
                            recordsTotal=0,
                            recordsFiltered=0))
            return
        elif 'active' in cycle_dt or 'previous' in cycle_dt or 'All cycles' in cycle_dt:
            cycle_dt = self._get_cycles(cycle_dt)

        cyclic_tasks = ['tasks.WrapperTask',
                        'tasks.PythonTask',
                        'tasks.SubprocessTask',
                        'chain.AllocateChainTask',
                        'chain.GroupChainTask']

        tasks = sorted(iter_tasks(app.events, search=search, type=cyclic_tasks),
                       key=lambda x: getattr(x[1], sort_by),
                       reverse=sort_order)

        tasks = list(map(self.format_task, tasks))
        
        cycle_tasks = []
        for _, task in tasks:
            task = as_dict(task)

            if cycle_dt and task['cycle_dt'] and task['cycle_dt'] not in cycle_dt:
                continue

            task['worker'] = getattr(task.get('worker',None),'hostname',None)
            cycle_tasks.append(task)

        cycle_tasks = self._squash_allocation(cycle_tasks)
            
        filtered_tasks = []
        i = 0
        for task in cycle_tasks:
            if i < start:
                i += 1
                continue
            if i >= (start + length):
                break
            
            filtered_tasks.append(task)
            i += 1

        self.write(dict(draw=draw, data=filtered_tasks,
                            recordsTotal=len(cycle_tasks),
                            recordsFiltered=len(cycle_tasks)))

    def format_task(self, args):
        uuid, task = args
        custom_format_task = self.application.options.format_task

        if custom_format_task:
            task = custom_format_task(copy.copy(task))
        return uuid, task