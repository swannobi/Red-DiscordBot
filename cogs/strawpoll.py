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
    
    def __init__(self, bot, settings, message, 
            author, poll_id, poll_length, sleep_time):
        self.bot = bot
        self.settings = settings
        self.message = message
        self.author = author
        self.poll_id = poll_id
        self.poll_title = ""
        self.poll_length = poll_length
        self.sleep_time = sleep_time
        self.start_time = time()

    # https://www.w3resource.com/python-exercises/python-basic-exercise-65.php
    def _time_left(self, seconds):
        days = seconds // (24 * 3600)
        seconds = seconds % (24 * 3600)
        hours = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        if days > 0:
            return "%d:%02d:%02d:%02d" % (days, hours, minutes, seconds)
        elif hours > 0:
            return "%02d:%02d:%02d" % (hours, minutes, seconds)
        else:
            return "%02d:%02d" % (minutes, seconds)

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
        self.poll_title = unescape(data['title'])
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
            embed.set_footer(text="{} left (update every {}s)".format(
                self._time_left(time_left), self.sleep_time))
        else: 
            embed.set_footer(text="as of {}".format(
                strftime('%A %B %-m, %Y @ %I:%M:%S%p ')))
        await self.bot.edit_message(self.message, embed=embed)

class Strawpoll:
    """Create, link, and update live results for a Strawpoll within Discord"""

    def __init__(self, bot, settings_path):
        self.bot = bot
        self.settings_path = settings_path
        self.settings = defaultdict(dict, dataIO.load_json(settings_path))
        self.active_poll_sessions = []
        self.active_poll_session_tasks = {}
        self.poll_sessions = []
        self.poll_session_tasks = {}

    def _new_server_settings(self, server_id):
        default_settings = {
            'refresh_emoji': '🔄',
            'poll_react_time': 300.0, # 5 minutes
            'bar_length': 30
        }
        self.settings[server_id] = default_settings
        dataIO.save_json(self.settings_path, self.settings)

    def _check_new_poll_tasks(self):
        for poll in self.active_poll_sessions:
            if poll not in self.active_poll_session_tasks:
                self.active_poll_session_tasks[poll] = asyncio.ensure_future(
                    self._countdown_poll(poll))
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
        self.active_poll_session_tasks = { 
            poll:task for poll,task in self.active_poll_session_tasks.items() 
            if not task.done()}

    async def check_polls(self):
        POLL_CHECK_RATE = 5 # seconds between each check for expired polls
        # while cog is loaded
        while self is self.bot.get_cog("Strawpoll"):
            current_time = time()
            self._check_new_poll_tasks()
            self._cancel_expired_poll_tasks(current_time)
            self._delete_expired_poll_sessions(current_time)
            self._remove_done_poll_tasks()
            await asyncio.sleep(POLL_CHECK_RATE)
        for poll in self.poll_session_tasks.keys():
            self.poll_session_tasks[poll].cancel()
        for poll in self.active_poll_session_tasks.keys():
            self.active_poll_session_tasks[poll].cancel()
        
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

    async def _countdown_poll(self, poll):
        settings = self.settings[poll.message.server.id]
        refresh_emoji = settings['refresh_emoji']
        try:
            while time()-poll.start_time < poll.poll_length:
                await poll.update_results()
                await asyncio.sleep(poll.sleep_time)
            await self.bot.delete_message(poll.message)
            poll.message = await self.bot.send_message(poll.message.channel,
                embed=discord.Embed(title="Loading results..."))
            await poll.update_results()
            await self.bot.add_reaction(poll.message, refresh_emoji)
            self.poll_sessions.append(poll)
            self.active_poll_sessions.remove(poll)
        except CancelledError:
            poll.poll_length = 0
            await poll.update_results()
            self.active_poll_sessions.remove(poll)
            raise CancelledError("Poll cancelled")

    async def _create_poll(self, message, channel, author, poll_id, poll_length):
        settings = self.settings[message.server.id]
        sleep_time = self._sleep_time(poll_length)
        poll = _Poll(self.bot, settings, 
                message, author, poll_id, poll_length, sleep_time)
        await poll.update_results()
        self.active_poll_sessions.append(poll)
    
    def _sleep_time(self, poll_length):
        if poll_length < 5*60: # 5 minutes
            return 1
        elif poll_length < 60*60: # 1 hour
            return 5
        elif poll_length < 60*60*12: # 12 hours
            return 10
        else: # more than 12 hours
            return 20
            
    def _poll_search(self, text, channel):
        text = text.lower()
        for poll in self.active_poll_sessions:
            if poll.message.server.id != channel.server.id:
                continue
            poll_title = poll.poll_title.lower()
            if text in poll_title:
                if poll in self.active_poll_session_tasks:
                    return poll
        return None

    async def _stop_poll(self, text, channel, author):
        poll = self._poll_search(text, channel)
        if poll is None:
            await self.bot.send_message(channel, 
                "Can't find any polls matching `" + text + "`.")
            return
        if not channel.permissions_for(author).manage_messages:
            if poll.author != author:
                await self.bot.send_message(channel, 
                    "Can't stop `" + poll.poll_title +
                    "` since you didn't create it.")
                return
        self.active_poll_session_tasks[poll].cancel()
        await self.bot.send_message(channel, 
            "Poll `" + poll.poll_title + "` stopped!")
        return
    
    async def _extend_poll(self, text, channel, author, hours):
        poll = self._poll_search(text, channel)
        if poll is None:
            await self.bot.send_message(channel, 
                "Can't find any polls matching `" + text + "`.")
            return
        if not channel.permissions_for(author).manage_messages:
            if poll.author != author:
                await self.bot.send_message(channel, 
                    "Can't extend `" + poll.poll_title +
                    "` since you didn't create it.")
                return
        old_length = poll.poll_length
        poll.poll_length += hours * 60 * 60
        await self.bot.send_message(channel, 
            "Poll `" + poll.poll_title + "` extended! `" +
            str(poll._time_left(old_length)) + "` -> `" + 
            str(poll._time_left(poll.poll_length)) + "`")
        return

    async def _poll_args_process(self, ctx, time, time_unit, text, multi):
        if ctx.message.server.id not in self.settings:
            self._new_server_settings(ctx.message.server.id)
        if len(text) <= 0:
            await self.bot.send_cmd_help(ctx)
            return
        time_unit = time_unit.lower()
        if time_unit.startswith('second'):
            poll_length = time # seconds
        elif time_unit.startswith('minute'):
            poll_length = time * 60 # minutes to seconds
        elif time_unit.startswith('hour'):
            poll_length = time * 60 * 60 # hours to seconds
        elif time_unit.startswith('day'):
            poll_length = time * 60 * 60 * 24 # days to seconds
        else:
            await self.bot.say(
                "Unknown time unit! Accepted units are:" + 
                "`second(s)`, `minute(s)`, `hour(s)`, `day(s)`.")
            await self.bot.send_cmd_help(ctx)
            return
        poll = ' '.join(text).split(';', 1)
        if len(poll) != 2:
            await self.bot.send_cmd_help(ctx)
            return
        title = poll[0]
        options = poll[1].split(';')
        options[:] = [option for option in options if option.strip()]
        response = _post_poll(title, options, multi)
        if not response:
            await self.bot.send_message(ctx.message.channel, 
                "Uh-oh, no response from Strawpoll received!")
            return
        if 'errorMessage' in response:
            await self.bot.say(
                "Strawpoll error: `{}`"
                .format(response['errorMessage']))
            await self.bot.send_cmd_help(ctx)
            return
        results_message = await self.bot.send_message(
            ctx.message.channel, 
            embed=discord.Embed(title="Loading strawpoll..."))
        await self._create_poll(
            results_message, ctx.message.channel, 
            ctx.message.author, response['id'], poll_length)
    
    @commands.group(pass_context=True, no_pm=True)
    async def strawpoll(self, ctx):
        """Interface for Strawpoll"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
    
    @strawpoll.command(pass_context=True, no_pm=True)
    async def stop(self, ctx, *search_terms):
        """
        Stop a poll on Strawpoll.me that matches search terms
        """
        await self._stop_poll(' '.join(search_terms),
            ctx.message.channel, ctx.message.author)

    @strawpoll.command(pass_context=True, no_pm=True)
    async def multi(self, ctx, time:float, time_unit:str, *text):
        """
        Host a multiple choice poll on Strawpoll.me with live results

        Options:
            time       How many `time_units` to run the poll 
                       (can be a decimal. eg. 0.1)
            time_unit  'seconds', 'minutes', 'hours', 'days'
            text       title;option 1;option 2;option 3(...)
        """
        await self._poll_args_process(ctx, time, time_unit, text,  True)


    @strawpoll.command(pass_context=True, no_pm=True)
    async def host(self, ctx, time:float, time_unit:str, *text):
        """
        Host a poll on Strawpoll.me with live results

        Options:
            time       How many `time_units` to run the poll 
                       (can be a decimal. eg. 0.1)
            time_unit  'seconds', 'minutes', 'hours', 'days'
            text       title;option 1;option 2;option 3(...)
        """
        await self._poll_args_process(ctx, time, time_unit, text, False)

    @strawpoll.command(pass_context=True, no_pm=True)
    async def extend(self, ctx, hours:float, *search_terms):
        """
        Extend a currently running poll that matches search terms
        
        Options:
            hours        How many hours to extend the poll
                         (can be a decimal. eg. 0.1)
            search_terms Search terms matching a currently running poll
        """
        await self._extend_poll(' '.join(search_terms),
            ctx.message.channel, ctx.message.author, hours)
    
    @checks.mod_or_permissions(manage_server=True)
    @strawpoll.command(pass_context=True, no_pm=True)
    async def config(self, ctx):
        """
        Display current strawpoll settings for this server
        """
        server_id = ctx.message.server.id
        if server_id not in self.settings:
            self._new_server_settings(server_id)
        settings = self.settings[server_id]
        settings_text = ''
        for setting, value in settings.items():
            settings_text += '{}: {}\n'.format(setting, value)
        await self.bot.say("```{}```".format(settings_text))

    @strawpoll.command(pass_context=True, no_pm=True)
    @checks.mod_or_permissions(manage_server=True)
    async def set(self, ctx, setting:str, value:str):
        """
        Adjust strawpoll default settings
    
        Settings:
            refresh_emoji    Manual refresh emoji once a poll ends
            poll_react_time  How long in seconds the refresh emoji stays active
            bar_length       How long the distribution bars in the embed are
        """
        server_id = ctx.message.server.id
        if server_id not in self.settings:
            self._new_server_settings(server_id)
        settings = self.settings[server_id]
        if setting is None or value is None:
            settings_text = ''
            for setting, value in settings.items():
                settings_text += '{}: {}\n'.format(setting, value)
            await self.bot.say("```{}```".format(settings_text))
            return
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

def check_files(settings_path):
    try:
        if not dataIO.is_valid_json(settings_path):
            raise FileNotFoundError("JSON file not valid")
    except FileNotFoundError:
        if not os.path.exists(os.path.dirname(settings_path)):
            print("Creating strawpoll data folder...")
            os.makedirs(os.path.dirname(settings_path))
        dataIO.save_json(settings_path, {})

def setup(bot):
    settings_path = "data/strawpoll/settings.json"
    check_files(settings_path)
    cog = Strawpoll(bot, settings_path)
    loop = asyncio.get_event_loop()
    loop.create_task(cog.check_polls())
    bot.add_cog(cog)