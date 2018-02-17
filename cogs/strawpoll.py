# Strawpoll functionality by Savestate for Red-DiscordBot

import urllib3
import certifi
import json
import traceback
import discord
import asyncio
from html import unescape
from time import sleep, time
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
    
    def __init__(self, bot, message, author, poll_id, start_time, poll_length):
        self.bot = bot
        self.message = message
        self.author = author
        self.poll_id = poll_id
        self.poll_length = poll_length
        self.start_time = start_time

    def _bar_creator(self, data, option):
        display_bar = " :: "
        BAR_LENGTH = 30
        for y in range(BAR_LENGTH):
            if (max(data['votes']) > 0):
                pct = float(
                    data['votes'][option])/float(max(data['votes']))
            else:
                continue
            if (pct != 0 and pct >= float(y)/float(BAR_LENGTH-1)):
                display_bar += '|'
        return display_bar

    async def update_results(self):
        data = _get_poll(self.poll_id)
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
            embed.set_footer(text="poll completed!")   
        await self.bot.edit_message(self.message, embed=embed)

class Strawpoll:
    """Create, link, and update live results for a Strawpoll within Discord"""

    def __init__(self, bot):
        self.bot = bot
        self.poll_sessions = []

    async def _say_usage(self):
        await self.bot.say(
        "strawpoll question;option1;option2 (...)\n"
        "strawpoll m question;option1;option2 (...)")
        
    async def _create_poll(self, message, author, poll_id):
        POLL_LENGTH = 60.0
        start_time = time()
        poll = _Poll(self.bot, message, author, 
            poll_id, start_time, POLL_LENGTH)
        while time()-start_time < POLL_LENGTH:
            await poll.update_results()
            sleep(1)
        await poll.update_results()
            
    @commands.command(pass_context=True)
    async def strawpoll(self, ctx, *text):
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
        for i in range(len(options)):
            options[i] = options[i].strip()
        # ~ fancy way of removing empty strings ~
        # if a string is empty, it evaluates to false.
        # so, if an option from options has content, then
        # assign that option for itself, otherwise it wont get
        # included in the splice. (took me a sec to parse it lol)
        options[:] = [option for option in options if option]
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
        asyncio.ensure_future(
            self._create_poll(
                results_message, ctx.message.author, response['id']))

def setup(bot):
    bot.add_cog(Strawpoll(bot))
    
