# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 GNS3 Technologies Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
import asyncio
import asyncio.subprocess

import logging
log = logging.getLogger(__name__)

READ_SIZE = 4096


class AsyncioRawCommandServer:
    """
    Expose a process on the network his stdoud and stdin will be forward
    on network
    """

    def __init__(self, command, replaces=[]):
        """
        :param command: Command to run
        :param replaces: List of tuple to replace in the output ex: [(b":8080", b":6000")]
        """
        self._command = command
        self._replaces = replaces

    @asyncio.coroutine
    def run(self, network_reader, network_writer):
        process = yield from asyncio.subprocess.create_subprocess_exec(*self._command,
                                                                       stdout=asyncio.subprocess.PIPE,
                                                                       stderr=asyncio.subprocess.STDOUT,
                                                                       stdin=asyncio.subprocess.PIPE)
        try:
            yield from self._process(network_reader, network_writer, process.stdout, process.stdin)
        except ConnectionResetError:
            network_writer.close()

    @asyncio.coroutine
    def _process(self, network_reader, network_writer, process_reader, process_writer):
        network_read = asyncio.async(network_reader.read(READ_SIZE))
        reader_read = asyncio.async(process_reader.read(READ_SIZE))

        while True:
            done, pending = yield from asyncio.wait(
                [
                    network_read,
                    reader_read
                ],
                return_when=asyncio.FIRST_COMPLETED)
            for coro in done:
                data = coro.result()

                if coro == network_read:
                    if network_reader.at_eof():
                        raise ConnectionResetError()

                    network_read = asyncio.async(network_reader.read(READ_SIZE))

                    process_writer.write(data)
                    yield from process_writer.drain()
                elif coro == reader_read:
                    if process_reader.at_eof():
                        raise ConnectionResetError()

                    reader_read = asyncio.async(process_reader.read(READ_SIZE))

                    for replace in self._replaces:
                        data = data.replace(replace[0], replace[1])
                    network_writer.write(data)
                    yield from network_writer.drain()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()

    command = ["nc", "localhost", "80"]
    server = AsyncioRawCommandServer(command)
    coro = asyncio.start_server(server.run, '127.0.0.1', 4444, loop=loop)
    s = loop.run_until_complete(coro)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    # Close the server
    s.close()
    loop.run_until_complete(s.wait_closed())
    loop.close()
