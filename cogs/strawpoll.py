# Strawpoll functionality by Savestate for Red-DiscordBot

import urllib3
import certifi
import json
import traceback
import discord
from discord.ext import commands

class Strawpoll:
    """Create, link, and update live results for a Strawpoll within Discord"""

    def __init__(self, bot):
        self.bot = bot
        self.poll_sessions = []
        
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
        if text[0] is 'm':
            multi = True
            text = text[1:]
        poll = ' '.join(text).split(';', 1)
        if len(poll) != 2:
            await self.bot.say(
                "strawpoll question;option1;option2 (...)\n"
                "strawpoll m question;option1;option2 (...)")
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
            await self.bot.say("Uh-oh, no response from Strawpoll received!")
            return
        if 'errorMessage' in response:
            await self.bot.say(
                "Strawpoll error: `{}`\n\n"
                "usage: \n"
                "strawpoll question;option1;option2 (...)\n"
                "strawpoll m question;option1;option2 (...)"
                .format(response['errorMessage']))
            return
        await self.bot.say('```{}```'.format(response))

def setup(bot):
    bot.add_cog(Strawpoll(bot))