import discord
from discord.ext import commands
from __main__ import send_cmd_help
import aiohttp
import json

class Taiga:
    """Taiga.io <--> Discord integration tool"""

    def __init__(self, bot):
        self.bot = bot
        self.auth_token = ''
        self.request_headers = {}
        self.active_board = 'swannobi-spongebot'

    @commands.group(pass_context=True, no_pm=False)
    async def taiga(self, ctx):
        """Interface for Taiga.io"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @taiga.command(pass_context=True, no_pm=False)
    async def register(self, ctx, username : str, password : str):
        """Attempts to retrieve a Taiga application auth token"""
        payload = { 'username' : username, 
                    'type' : 'normal',
                    'password' : password }
        async with aiohttp.post('https://api.taiga.io/api/v1/auth', data=payload) as response:
            result = await response.json()
            if(response.status == 200):
                self.auth_token = result['auth_token']
                self.request_headers['Authorization'] = "Bearer "+self.auth_token
                await self.bot.say("All set. Working as `"+result['username']+"`.")
            else:
                await self.bot.say("Something went wrong.\n"+str(result))

    @taiga.command()
    async def ready(self):
        """Gets all stories in Ready from the currently active board."""
#        async with aiohttp.get('https://api.taiga.io/api/v1/projects/235600') as response:
#        async with aiohttp.get('https://api.taiga.io/api/v1/projects/by_slug?slug='+self.active_board) as response:
        #Get Ready status
        async with aiohttp.get('https://api.taiga.io/api/v1/userstory-statuses?project=235600') as statuses_response:
            ready_id = [status for status in await statuses_response.json() if status['slug'] == "ready"][0]['id']
        #Get Ready stories
        async with aiohttp.get('https://api.taiga.io/api/v1/userstories?project=235600', headers=self.request_headers) as response:
            story = await response.json()
            for us in story:
                if us['status'] == ready_id:
                    async with aiohttp.get('https://api.taiga.io/api/v1/userstories/'+str(us['id'])) as us_detail:
                        response_detail = await us_detail.json()
                        await self.bot.say(embed=self._form_userstory_embed(response_detail))
                        return

    def _form_userstory_embed(self, us):
        """Private method to handle specific logic for forming an embed."""
        print(json.dumps(us, sort_keys=True))
        embed = discord.Embed()
        if us['project_extra_info']['logo_small_url'] is not None:
            embed.set_author(name=us['subject'], icon_url=str(us['project_extra_info']['logo_small_url']))
        if us['assigned_to_extra_info']['photo'] is not None:
            embed.set_thumbnail(url=us['owner_extra_info']['photo'])
        embed.description=us['description']
        embed.colour=discord.Colour(0xffffff)
        embed.set_footer(text="Discord-Taiga integration by Swann.")
        return embed

def setup(bot):
    bot.add_cog(Taiga(bot))

