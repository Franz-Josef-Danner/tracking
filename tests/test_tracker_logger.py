import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.util.tracker_logger import configure_logger, TrackerLogger


def test_configure_logger_debug():
    logger = configure_logger(debug=True)
    assert logger.level == 10  # logging.DEBUG


def test_tracker_logger_methods(caplog):
    logger = configure_logger(debug=True)
    tlogger = TrackerLogger()
    with caplog.at_level(logger.level):
        tlogger.info('info')
        tlogger.warn('warn')
        tlogger.error('error')
        tlogger.debug('debug')
    assert 'info' in caplog.text
    assert 'warn' in caplog.text
    assert 'error' in caplog.text
    assert 'debug' in caplog.text


def test_configure_logger_file(tmp_path):
    log_file = tmp_path / "test.log"
    logger = configure_logger(debug=True, log_file=log_file)
    logger.info('file')
    for h in logger.handlers:
        if hasattr(h, 'flush'):
            h.flush()
    assert log_file.exists()
    assert 'file' in log_file.read_text()

