# Strawpoll functionality by Savestate for Red-DiscordBot

import urllib3
import certifi
import json
import traceback
import discord
import asyncio
import os
from collections import defaultdict
from .utils import checks
from .utils.dataIO import dataIO
from concurrent.futures import CancelledError
from html import unescape
from time import sleep, time, strftime
from discord.ext import commands

def _get_poll(poll_id):
    # https://strawpoll.me/api/v2/polls/{poll_id}
    https = urllib3.PoolManager(
        cert_reqs='CERT_REQUIRED',
        ca_certs=certifi.where())
    try:
        request = https.request( 'GET', 
            'https://strawpoll.me/api/v2/polls/' + str(poll_id),
            retries=3, timeout=3.0)
        json_response = json.loads(request.data.decode('utf-8'))
    except urllib3.exceptions.HTTPError:
        return None
    except json.decoder.JSONDecodeError:
        return None
    return json_response
    
def _post_poll(title, options, multi):
    # build json request
    data = {
        'title': title,
        'options': options,
        'multi': multi,
        'dupcheck': 'normal',
        'captcha': False }
    encoded_data = json.dumps(data).encode('utf-8')
    # urllib3 pool manager in https mode
    https = urllib3.PoolManager(
        cert_reqs='CERT_REQUIRED',
        ca_certs=certifi.where())
    try:
        request = https.request(
            'POST', 'https://strawpoll.me/api/v2/polls',
            body=encoded_data, headers={
                'Content-Type': 'application/json',
                'Accept-Charset': 'utf-8'
            },
            retries=3, timeout=3.0)
        json_response = json.loads(request.data.decode('utf-8'))
    except urllib3.exceptions.HTTPError:
        return None
    return json_response

class _Poll:
    """Internal poll class for Strawpoll cog"""
    
    def __init__(self, bot, settings, message, author, poll_id, poll_length):
        self.bot = bot
        self.settings = settings
        self.message = message
        self.author = author
        self.poll_id = poll_id
        self.poll_length = poll_length
        self.start_time = time()

    def _bar_creator(self, data, option):
        display_bar = " :: "
        bar_length = self.settings['bar_length']
        for y in range(bar_length):
            if (max(data['votes']) > 0):
                pct = float(
                    data['votes'][option])/float(max(data['votes']))
            else:
                continue
            if (pct != 0 and pct >= float(y)/float(bar_length-1)):
                display_bar += '|'
        return display_bar

    async def update_results(self):
        data = _get_poll(self.poll_id)
        if data is None:
            await self.bot.edit_message(self.message, 
                embed=discord.Embed(title="Error receiving strawpoll data!"))
        embed=discord.Embed(title=unescape(data['title']), 
            url='https://strawpoll.me/' + str(self.poll_id), 
            description="Strawpoll Results", color=self.author.color)
        embed.set_author(
            name=self.author.nick if self.author.nick else self.author.name, 
            icon_url=self.author.avatar_url)
        for option in range(len(data['options'])):
            embed.add_field(inline=False, 
                name="{} ({} Vote{})".format(
                    unescape(data['options'][option]),
                    str(data['votes'][option]),
                    '' if (data['votes'][option] == 1) else 's'),
                value=self._bar_creator(data, option))
        time_left = round(self.poll_length-(time()-self.start_time))
        if (time_left > 0):
            embed.set_footer(text="{} sec{} left".format(
                str(time_left), '' if (time_left == 1) else 's'))
        else: 
            embed.set_footer(text="as of {}".format(
                strftime('%A %B %-m, %Y @ %I:%M:%S%p ')))
        await self.bot.edit_message(self.message, embed=embed)

class Strawpoll:
    """Create, link, and update live results for a Strawpoll within Discord"""
    
    def __init__(self, bot, settings_path):
        self.bot = bot
        self.settings_path = settings_path
        self.poll_sessions = []
        self.poll_session_tasks = {}
        try:
            if not dataIO.is_valid_json(settings_path):
                raise FileNotFoundError("JSON file not valid")
            settings = dataIO.load_json(settings_path)
            self.settings = defaultdict(dict, settings)
        except FileNotFoundError:
            self.settings = {}
            if not os.path.exists(os.path.dirname(settings_path)):
                print("Creating strawpoll data folder...")
                os.makedirs(os.path.dirname(settings_path))
            dataIO.save_json(settings_path, self.settings)

    def _new_server_settings(self, server_id):
        default_settings = {
            'refresh_emoji': '🔄',
            'poll_length': 60.0,
            'poll_react_time': 1800.0, # 30 minutes
            'bar_length': 30
        }
        self.settings[server_id] = default_settings
        dataIO.save_json(self.settings_path, self.settings)

    async def _say_usage(self):
        await self.bot.say(
        "```strawpoll question;option1;option2 (...)\n"
        "strawpoll m question;option1;option2 (...)```")

    def _check_new_poll_tasks(self):
        for poll in self.poll_sessions:
            if poll not in self.poll_session_tasks:
                self.poll_session_tasks[poll] = asyncio.ensure_future(
                    self._check_reacts(poll))

    def _cancel_expired_poll_tasks(self, current_time):
        for poll in self.poll_session_tasks.keys():
            server_id = poll.message.server.id
            poll_react_time = self.settings[server_id]['poll_react_time']
            if current_time-poll.start_time > poll_react_time:
                self.poll_session_tasks[poll].cancel()
 
    def _delete_expired_poll_sessions(self, current_time):
        trimmed_poll_sessions = []
        for poll in self.poll_sessions:
            server_id = poll.message.server.id
            poll_react_time = self.settings[server_id]['poll_react_time']
            if current_time-poll.start_time < poll_react_time:
                trimmed_poll_sessions.append(poll)
        self.poll_sessions = trimmed_poll_sessions

    def _remove_done_poll_tasks(self):
        self.poll_session_tasks = { 
            poll:task for poll,task in self.poll_session_tasks.items() 
            if not task.done()}

    async def check_polls(self):
        while self is self.bot.get_cog("Strawpoll"):
            current_time = time()
            self._check_new_poll_tasks()
            self._cancel_expired_poll_tasks(current_time)
            self._delete_expired_poll_sessions(current_time)
            self._remove_done_poll_tasks()
            await asyncio.sleep(5)
        for poll in self.poll_session_tasks.keys():
            self.poll_session_tasks[poll].cancel()
        
    async def _check_reacts(self, poll):
        settings = self.settings[poll.message.server.id]
        refresh_emoji = settings['refresh_emoji']
        try:
            while True:
                react = await self.bot.wait_for_reaction(refresh_emoji, 
                    message=poll.message)
                await poll.update_results()
                await asyncio.sleep(0.5) # don't remove reaction too fast
                await self.bot.remove_reaction(
                    poll.message, refresh_emoji, react.user)
        except CancelledError:
            await self.bot.clear_reactions(poll.message)
            raise CancelledError("Poll cancelled")
            
    async def _create_poll(self, message, channel, author, poll_id):
        settings = self.settings[message.server.id]
        refresh_emoji = settings['refresh_emoji']
        poll_length = settings['poll_length']
        poll = _Poll(self.bot, settings, 
                message, author, poll_id, poll_length)
        while time()-poll.start_time < poll_length:
            await poll.update_results()
            await asyncio.sleep(1)
        await self.bot.delete_message(poll.message)
        poll.message = await self.bot.send_message(channel,
            embed=discord.Embed(title="Loading results..."))
        await poll.update_results()
        await self.bot.add_reaction(poll.message, refresh_emoji)
        self.poll_sessions.append(poll)
    
    @commands.command(pass_context=True, no_pm=True)
    async def strawpoll(self, ctx, *text):
        if ctx.message.server.id not in self.settings:
            self._new_server_settings(ctx.message.server.id)
        multi = False
        if len(text) <= 0:
            await self._say_usage()
            return
        if text[0] is 'm':
            multi = True
            text = text[1:]
        poll = ' '.join(text).split(';', 1)
        if len(poll) != 2:
            await self._say_usage()
            return
        options = poll[1].split(';')
        # ~ fancy way of removing empty strings ~
        # if a string is empty, it evaluates to false.
        # so, if an option from options has content, then
        # assign that option for itself, otherwise it wont get
        # included in the splice. (took me a sec to parse it lol)
        options[:] = [option for option in options if option.strip()]
        response = _post_poll(poll[0], options, multi)
        if not response:
            await self.bot.send_message(ctx.message.channel, 
                "Uh-oh, no response from Strawpoll received!")
            return
        if 'errorMessage' in response:
            await self.bot.say(
                "Strawpoll error: `{}`"
                .format(response['errorMessage']))
            await self._say_usage()
            return
        results_message = await self.bot.send_message(
            ctx.message.channel, 
            embed=discord.Embed(title="Loading strawpoll..."))
        await self._create_poll(
            results_message, ctx.message.channel, 
            ctx.message.author, response['id'])
    
    @commands.command(name="strawpollset", pass_context=True)
    @checks.mod_or_permissions(manage_server=True)
    async def strawpoll_settings(self, ctx, *text):
        server_id = ctx.message.server.id
        if server_id not in self.settings:
            self._new_server_settings(server_id)
        settings = self.settings[server_id]
        if len(text) < 2:
            settings_text = ''
            for setting, value in settings.items():
                settings_text += '{}: {}\n'.format(setting, value)
            await self.bot.say("```{}```".format(settings_text))
            return
        setting = text[0]
        value = text[1]
        if setting not in settings:
            await self.bot.say("`{}` is not a valid setting!".format(setting))
            return
        old_value = settings[setting]
        if isinstance(settings[setting], int):
            settings[setting] = int(float(value))
        if isinstance(settings[setting], float):
            settings[setting] = float(value)
        if isinstance(settings[setting], str):
            settings[setting] = str(value)
        await self.bot.say("`{}` updated. `{}` -> `{}`".format(
            setting, old_value, settings[setting]))
        dataIO.save_json(self.settings_path, self.settings)

def setup(bot):
    cog = Strawpoll(bot, "data/strawpoll/settings.json")
    loop = asyncio.get_event_loop()
    loop.create_task(cog.check_polls())
    bot.add_cog(cog)