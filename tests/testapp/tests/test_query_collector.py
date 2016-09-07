from django.contrib.auth.models import Group
from django.core import signals
from django.db import connection, reset_queries
from django_performance_testing.queries import QueryCollector
from django_performance_testing.signals import results_collected


def test_captures_queries(db):
    with QueryCollector() as qc_insert:
        Group.objects.create(name='foo')
    assert len(qc_insert.queries) == 1
    with QueryCollector() as qc_select:
        list(Group.objects.all())
    assert len(qc_select.queries) == 1
    with QueryCollector() as qc_update:
        Group.objects.update(name='bar')
    assert len(qc_update.queries) == 1
    with QueryCollector() as qc_delete:
        Group.objects.all().delete()
    delete_queries = list(
        x['sql'] for x in qc_delete.queries if 'DELETE' in x['sql'])
    assert len(delete_queries) != 0, qc_delete.queries


def test_resets_connection_debugcursor_into_expected_state(db):
    assert connection.force_debug_cursor is False, \
        'before QC with non-debug connection'
    with QueryCollector():
        assert connection.force_debug_cursor is True, 'inside QC'
    assert connection.force_debug_cursor is False, \
        'after QC with non-debug connection'

    try:
        connection.force_debug_cursor = True
        with QueryCollector():
            assert connection.force_debug_cursor is True, 'inside QC'
        assert connection.force_debug_cursor is True, \
            'after QC with debug connection'
    finally:
        connection.force_debug_cursor = False


def test_ctx_managers_can_be_nested(db):
    captured = {}

    def capture_signals(signal, sender, results, context):
        captured.setdefault(sender, [])
        captured[sender].append(results)

    results_collected.connect(capture_signals)
    try:
        with QueryCollector() as outer:
            list(Group.objects.all())
            list(Group.objects.all())
            with QueryCollector() as inner:
                list(Group.objects.all())
        assert {outer: [[3]], inner: [[1]]} == captured
    finally:
        results_collected.disconnect(capture_signals)


def test_collector_can_live_through_request_reseting_queries(db):
    with QueryCollector() as qc:
        list(Group.objects.all())
        signals.request_started.send(sender=None)
        Group.objects.update(name='df')
        reset_queries()
        Group.objects.all().delete()

    assert len(qc.queries) == 3
