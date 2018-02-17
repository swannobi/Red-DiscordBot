# Strawpoll functionality by Savestate for Red-DiscordBot

import urllib3
import certifi
import json
import traceback
import discord
import asyncio
from time import sleep
from discord.ext import commands

class Strawpoll:
    """Create, link, and update live results for a Strawpoll within Discord"""

    def __init__(self, bot):
        self.bot = bot
        self.poll_sessions = []
        
    async def _say_usage(self):
        await self.bot.say(
        "strawpoll question;option1;option2 (...)\n"
        "strawpoll m question;option1;option2 (...)")
        
    async def _update_results(self, message, author, poll_id, countdown):
        for x in range(countdown):
            data = self._get_poll(poll_id)
            embed=discord.Embed(title=data['title'], 
                url='http://strawpoll.me/' + str(poll_id), 
                description="Strawpoll Results", color=author.color)
            embed.set_author(name=author.nick, icon_url=author.avatar_url)
            for option in range(len(data['options'])):
                BAR_LENGTH = 30
                display_bar = ''
                for y in range(BAR_LENGTH):
                    if (max(data['votes']) > 0):
                        pct = float(data['votes'][option])/float(max(data['votes']))
                    else:
                        pct = 0.0
                    if (pct == 0.0):
                        continue
                    display_bar += '|' if (pct >= float(y)/float(BAR_LENGTH-1)) else ''
                embed.add_field(inline=False, 
                    name="{} ({} Vote{})".format(
                        data['options'][option],
                        str(data['votes'][option]),
                        '' if (data['votes'][option] == 1) else 's'),
                    value=" :: {}".format(display_bar))
            time_left = countdown-x-1
            if (time_left > 0):
                embed.set_footer(text="{} sec{} left".format(
                    str(time_left), '' if (time_left == 1) else 's'))
            else: 
                embed.set_footer(text="poll completed!")                
            await self.bot.edit_message(message, embed=embed)
            sleep(1)
        
    def _get_poll(self, poll_id):
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
        
    def _post_poll(self, title, options, multi):
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
        response = self._post_poll(poll[0], options, multi)
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
            ctx.message.channel, 'Loading strawpoll data...')
        asyncio.ensure_future(
            self._update_results(
                results_message, ctx.message.author, response['id'], 60))

def setup(bot):
    bot.add_cog(Strawpoll(bot))