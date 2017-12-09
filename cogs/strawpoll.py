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
        
    @commands.command(pass_context=True)
    async def strawpoll(self, ctx):
        https = urllib3.PoolManager(
            cert_reqs='CERT_REQUIRED',
            ca_certs=certifi.where())
        data = {
            'title': 'test poll title',
            'options': [
                'option 1',
                'option 2', 
                'option 3',
                'option 4???'],
            'multi': True,
            'dupcheck': 'normal',
            'captcha': False }
        encoded_data = json.dumps(data).encode('utf-8')
        try:
            request = https.request(
                'POST', 'https://strawpoll.me/api/v2/polls',
                body=encoded_data, headers={
                    'Content-Type': 'application/json',
                    'Accept-Charset': 'utf-8'
                },
                retries=3, timeout=3.0)
            json_response = json.loads(request.data.decode('utf-8'))
        except urllib3.exceptions.RequestError as e:
            await self.bot.send_message(ctx.message.channel, "oooooops lmao")
            return
        await self.bot.send_message(ctx.message.channel,
            ''.join(['http://www.strawpoll.me/', str(json_response['id'])]))

def setup(bot):
    bot.add_cog(Strawpoll(bot))