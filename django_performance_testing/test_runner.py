# TODO: app.ready happens before the command is imported - how to test?
from django.conf import settings
from django.test import utils
from django_performance_testing.reports import WorstReport
from django_performance_testing.utils import BeforeAfterWrapper
from django_performance_testing.context import scoped_context
from django_performance_testing import core as djpt_core
import unittest

orig_get_runner = utils.get_runner


class DjptDjangoTestRunnerMixin(object):
    pass


class DjptTestRunnerMixin(object):

    def run(self, *a, **kw):
        """
            as self.stopTestRun is ran before the actual results were printed,
            need to override run() to print things after
        """
        self.djpt_worst_report = WorstReport()
        retval = super(DjptTestRunnerMixin, self).run(*a, **kw)
        if getattr(settings, 'DJPT_PRINT_WORST_REPORT', True):
            self.djpt_worst_report.render(self.stream)
        return retval


def wrap_cls_method(cls, method_name, collector_id, ctx_key):
    target_method = getattr(cls, method_name)
    has_been_patched_flag = 'ctx_manager'
    if hasattr(target_method, has_been_patched_flag):
        return
    ctx_value = '{} ({})'.format(
        method_name, unittest.util.strclass(cls))
    for collector in DjptTestRunnerMixin.collectors[collector_id]:
        BeforeAfterWrapper(
            cls, method_name, context_manager=collector)
    ctx = scoped_context(key=ctx_key, value=ctx_value)
    BeforeAfterWrapper(
        cls, method_name, context_manager=ctx)
    target_method.__dict__[has_been_patched_flag] = True


def get_runner_with_djpt_mixin(*a, **kw):
    test_runner_cls = orig_get_runner(*a, **kw)

    class DjptTestRunner(DjptTestRunnerMixin, test_runner_cls.test_runner):
        pass

    class DjptDjangoTestRunner(DjptDjangoTestRunnerMixin, test_runner_cls):

        test_runner = DjptTestRunner

    def addTest(suite_self, test):
        retval = orig_suite_addTest(suite_self, test)
        test_cls = test.__class__
        is_test = hasattr(test, '_testMethodName')
        if is_test:
            wrap_cls_method(
                cls=test_cls,
                method_name=test._testMethodName,
                collector_id='test method',
                ctx_key='test name'
            )
            wrap_cls_method(
                cls=test_cls,
                method_name='setUp',
                collector_id='test setUp',
                ctx_key='setup method',
            )
            wrap_cls_method(
                cls=test_cls,
                method_name='tearDown',
                collector_id='test tearDown',
                ctx_key='teardown method',
            )
        return retval

    def fn_to_id(fn):
        return fn.__code__.co_filename

    if fn_to_id(addTest) != fn_to_id(DjptDjangoTestRunner.test_suite.addTest):
        orig_suite_addTest = DjptDjangoTestRunner.test_suite.addTest
        DjptDjangoTestRunner.test_suite.addTest = addTest
    return DjptDjangoTestRunner


def integrate_into_django_test_runner():
    utils.get_runner = get_runner_with_djpt_mixin
    DjptTestRunnerMixin.collectors = {}
    DjptTestRunnerMixin.limits = {}
    for collector_id in ['test method', 'test setUp', 'test tearDown']:
        collectors = DjptTestRunnerMixin.collectors[collector_id] = []
        limits = DjptTestRunnerMixin.limits[collector_id] = []
        for limit_cls in djpt_core.limits_registry.name2cls.values():
            collector = limit_cls.collector_cls(id_=collector_id)
            collectors.append(collector)
            limit = limit_cls(collector_id=collector_id, settings_based=True)
            limits.append(limit)
