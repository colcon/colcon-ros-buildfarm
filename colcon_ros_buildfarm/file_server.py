# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

from functools import partial
from http.server import SimpleHTTPRequestHandler
import os
import posixpath
from socketserver import TCPServer
from threading import Thread
import urllib

from colcon_core.logging import colcon_logger

logger = colcon_logger.getChild(__name__)


class _SimpleHTTPRequestHandler(SimpleHTTPRequestHandler):
    """
    Backport from Python 3.7 of the directory arg to SimpleHTTPRequestHandler.

    The translate_path function is the only one that appears to have needed
    changes to support this feature.
    """

    def __init__(self, *args, directory=None, **kwargs):
        if directory is None:
            directory = os.getcwd()
        self._directory = directory
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        # abandon query parameters
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        # Don't forget explicit trailing slash when normalizing. Issue17324
        trailing_slash = path.rstrip().endswith('/')
        try:
            path = urllib.parse.unquote(path, errors='surrogatepass')
        except UnicodeDecodeError:
            path = urllib.parse.unquote(path)
        path = posixpath.normpath(path)
        words = path.split('/')
        words = filter(None, words)
        path = self._directory
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                # Ignore components that are not a simple file/directory name
                continue
            path = os.path.join(path, word)
        if trailing_slash:
            path += '/'
        return path

    def log_message(self, format_str, *args):
        logger.debug('{} - - [{}] {}'.format(
            self.address_string(),
            self.log_date_time_string(),
            (format_str % args)))


class SimpleFileServer:
    """A dirt-simple HTTP file server."""

    def __init__(self, directory):
        """
        Create a new SimpleFileServer.

        :param directory: The directory to serve
        """
        self._directory = directory
        self._thread = Thread(target=self._run)

    def start(self, port=None):
        """
        Start the server thread.

        :returns: The hostname and port to connect to
        """
        if port is None:
            port = 0
        self._server = TCPServer(
            ('127.0.0.1', port),
            partial(_SimpleHTTPRequestHandler, directory=self._directory))
        self._thread.start()
        host, port = self._server.socket.getsockname()
        logger.info(
            'File server listening at http://{host}:{port}/'.format_map(
                locals()))
        return host, port

    def stop(self):
        """Shutdown the server thread."""
        logger.debug('File server is shutting down...')
        self._server.shutdown()
        self._thread.join()
        self._server = None
        logger.info('File server has shut down')

    def _run(self):
        self._server.serve_forever()
