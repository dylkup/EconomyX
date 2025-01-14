import discord
import re
import random
import asyncio
import aiosqlite
from discord.ext import commands
from discord.ext import tasks
from datetime import datetime
from .utils.botviews import Confirm
from .utils import player as Player
OWNER_ID = 267410788996743168

class stocks(commands.Cog, command_attrs=dict(name='Stocks')):
    """
    Stock commands (except investments).
    """
    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        await self.bot.db.execute("CREATE TABLE IF NOT EXISTS e_stocks (stockid int, name text, points double, previouspoints double, ownerid int, created text, icon_url blob)")
        await self.bot.db.execute("CREATE TABLE IF NOT EXISTS e_invests (stockid int, userid int, invested int, stockname text, invested_at double, invested_date blob)")
        self.main_stock_loop.start()

    async def cog_unload(self):
        self.main_stock_loop.cancel()
        
    @tasks.loop(seconds=900)
    async def main_stock_loop(self):
        await self.bot.wait_until_ready()
        c = await self.bot.db.execute("SELECT * FROM e_stocks")
        all_stocks = await c.fetchall()
        for s in all_stocks:
            previous_amount = s[2]
            bruh = random.choice([True, False]) # true = add, false = subtract
            amount = random.uniform(0.1,1.1)
            amount = round(amount,2)
            if bruh:
                await self.bot.db.execute("UPDATE e_stocks SET points = (points + ?) WHERE stockid = ?",(amount, s[0]))
            if not bruh:
                cv = s[2] # current value
                if (cv - amount) < 0:
                    amount = 0 # we dont want it to go negative
                else:
                    await self.bot.db.execute("UPDATE e_stocks SET points = (points - ?) WHERE stockid = ?",(amount, s[0]))
            #then update previous amount for e$stock view 
            await self.bot.db.execute("UPDATE e_stocks SET previouspoints = ? WHERE stockid = ?", (previous_amount, s[0]))
        print(f"{len(all_stocks)} stocks updated")
    
    @commands.command(aliases=["port","pf"])
    async def portfolio(self, ctx, user: discord.User = None):
        """Views a players stock portfolio. Includes all investments, and owned stocks."""
        player = await Player.get(ctx.author.id, self.bot)
        if player is None:
            await ctx.send("You dont have a profile! Get one with `e$register`.")
            return
        if user is None:
            user = ctx.author
        embed = discord.Embed(title=f"{str(user)}'s stock portfolio",description=f"`ID: {user.id}`",color=player.profile_color)
        playerstock = await self.bot.get_stock_from_player(ctx.author.id)
        if playerstock is None:
            embed.add_field(name="Owned stock",value="None")
        else:
            embed.add_field(name="Owned Stock",value=f"{playerstock[1]} [`{playerstock[0]}`]")
            tl = self.bot.utc_calc(playerstock[5], type="R")
            embed.add_field(name="Stock Created",value=tl)
            embed.add_field(name="Stock Points",value=f"{round(playerstock[2],1)}")
        c = await self.bot.db.execute("SELECT * FROM e_invests WHERE userid = ?",(user.id,))
        playerinvests = await c.fetchall()
        if playerinvests is None:
            embed.add_field(name="Invested Stocks",value="None")
        else:
            t = ""
            for i in playerinvests:
                tl = self.bot.utc_calc(i[5], type='R')
                t = t + (f"{i[3]} [`{i[0]}`]: invested ${i[2]} @ {round(i[4],1)} points, {tl}\n")
            if t == "":
                t = "None!"
            embed.add_field(name="Invests",value=t,inline=False)
        await ctx.send(embed=embed)
        
    @commands.group(aliases=["stocks","st"], invoke_without_command=True)
    async def stock(self, ctx):
        """Stocks management commands. Invoking without a command shows list of top stocks."""
        player = await Player.get(ctx.author.id, self.bot)
        cur = await self.bot.db.execute("SELECT * FROM e_stocks ORDER BY points DESC;")
        allstocks = await cur.fetchall()
        try:
            cur = await self.bot.db.execute("SELECT SUM(invested) FROM e_invests")
            total_invested = await cur.fetchone()
        except aiosqlite.OperationalError:
            return await ctx.send("An internal error occured while attempting to calculate the total amount invested into stocks")

        cur = await self.bot.db.execute("SELECT SUM(points) FROM e_stocks")
        total_points = await cur.fetchone()
        embed = discord.Embed(
            title="All Stocks",
            description=f"Total amount invested: ${total_invested[0]}, Total stock points: {round(total_points[0], 2)}",
            color=player.profile_color
            )
        counter = 0
        for i in allstocks:
            if counter > 10:
                break
            cur = await self.bot.db.execute("SELECT COUNT(*) FROM e_invests WHERE stockid = ?",(i[0],))
            investor_count = await cur.fetchone()
            tl = self.bot.utc_calc(i[5], type="R")
            embed.add_field(name=i[1],value=f"ID: {i[0]}, Points: {round(i[2],1)}, {investor_count[0]} Investors, Created {tl}")
            counter += 1
        await ctx.send(embed=embed)
    
    @stock.command(description="Views a specified stock.", aliases=["info","show"])
    async def view(self, ctx, name_or_id):
        """Shows a stock. You can specify a name or ID."""
        stock = await self.bot.get_stock(name_or_id)
        if not stock:
            return await ctx.send("I couldn't find that stock, check the name or ID again. Note: Names are case sensitive.")
        embed = discord.Embed(title=f"{stock[1]}", description=f"ID: {stock[0]}")
        tl1 = self.bot.utc_calc(stock[5], type="R")
        tl2 = self.bot.utc_calc(stock[5], type="F")
        embed.add_field(name="Stock Created",value=f"{tl2} / {tl1}")
        upordown = "UP" if stock[3] < stock[2] else "DOWN"
        embed.add_field(name="Stock Points",value=f"`{round(stock[2],1)}`, {upordown} from `{round(stock[3],1)}` points")
        embed.add_field(name="Owner", value=f"<@{stock[4]}>", inline=False)
        if str(stock[6]).startswith("http"):
            embed.set_thumbnail(url=stock[6])
        await ctx.send(embed=embed)
        
    @stock.command(aliases=["c"], description="Creates a new stock.")
    async def create(self, ctx, name, icon_url):
        """Creates a stock. A name and direct link to an image are required."""
        player = await Player.get(ctx.author.id, self.bot)
        if player.balance < 1000:
            return await ctx.send(f"Sorry. You have to have $1000 to create a stock.\nYour balance: ${player.balance}")
        playerstock = await self.bot.get_stock_from_player(ctx.author.id)
        if playerstock is not None:
            return await ctx.send("You already have a stock. If you want to edit it, use `e$stock edit`")
        if len(name) > 5:
            return await ctx.send("The stock name must be less than or equal to 5 characters.")
        if not name.isalpha():
            return await ctx.send("Stock names must be letters only.")
        name = name.upper()
        result = re.findall(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", icon_url)
        if result == []:
            return await ctx.send("Invalid URL provided.")
        
        stockid = random.randint(1000,9999)
        view = Confirm()
        msg = await ctx.send(f"Stock name: {name}\nIcon URL: <{icon_url}>\nID: {stockid}\nStarting points: 10\n**Are you sure you want to create this stock for $1000?**", view=view)
        await view.wait()
        if view.value is None:
            return await msg.edit(content=f"Timed out after 3 minutes.")
        elif view.value:
            stock_created_at = discord.utils.utcnow()
            await self.bot.db.execute("UPDATE e_users SET bal = (bal - 1000) WHERE id = ?",(ctx.author.id,))
            await self.bot.db.execute("INSERT INTO e_stocks VALUES (?, ?, 10.0, 10.0, ?, ?, ?)",(stockid, name, ctx.author.id, stock_created_at, icon_url,))
            await msg.delete()
            return await ctx.reply('👍')
        else:
            return await msg.delete()
            
    
    @stock.command(description="Deletes an owned stock. Please consider renaming first, before deleting. You do not get refunded the money you paid to create the stock.")
    async def delete(self, ctx):
        await Player.get(ctx.author.id, self.bot) # Check if player exists
        playerstock = await self.bot.get_stock_from_player(ctx.author)
        if playerstock is None:
            return await ctx.send("You don't have a stock. If you want make one, use `e$stock create <name>`")
        
        cur = await self.bot.db.execute("SELECT COUNT(*) FROM e_invests WHERE stockid = ?",(playerstock[0],))
        investor_count = await cur.fetchone()
        cur = await self.bot.db.execute("SELECT SUM(invested) FROM e_invests WHERE stockid = ?",(playerstock[0],))
        sum_invested = await cur.fetchone()
        tl = self.bot.utc_calc(playerstock[5])
        view = Confirm()
        msg = await ctx.send(f"**Are you sure you want to delete your stock?**\nStock name: {playerstock[1]}, Stock ID: {playerstock[0]}, Current points: {playerstock[2]}\nInvestors: {investor_count[0]}, Total amount invested: ${sum_invested[0]}\nCreated {tl} ago\n__Investments will not be deleted. Investors will be refunded the amount they invested. You will not be refunded.__", view=view)
        await view.wait()
        if view.value is None:
            return await msg.edit(f"Timed out after 3 minutes. Your stock wasn't deleted.")
        elif view.value:
            await self.bot.db.execute("DELETE FROM e_stocks WHERE ownerid = ?",(ctx.author.id,))
            await msg.delete()
            await ctx.reply('👍')
        else:
            await msg.delete()
        
    @stock.command(aliases=["e"], description="Edits a stock. Don't invoke with arguments.")
    async def edit(self, ctx):
        await Player.get(ctx.author.id, self.bot)
        playerstock = await self.bot.get_stock_from_player(ctx.author.id)
        if playerstock is None:
            return await ctx.send("You don't have a stock. If you want make one, use `e$stock create <name>`")
        
        # todo: make a view for this \/ \/
        rlist = ['1\N{variation selector-16}\N{combining enclosing keycap}', '2\N{variation selector-16}\N{combining enclosing keycap}', '❌']
        confirm = await ctx.send(f"What do you want to edit?\n{rlist[0]} : `Name`\n{rlist[1]} : `Icon`")
        for r in rlist:
            await confirm.add_reaction(r)
        def check(r, u):
            return r.message.id == confirm.id and str(r.emoji) in rlist and u.id == ctx.author.id
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30, check=check)
        except asyncio.TimeoutError:
            try: await confirm.clear_reactions()
            except: pass
            await confirm.edit("Timed out after 30s.")
        if str(reaction) == rlist[0]:
            msg = await ctx.reply("What should the new stock name be? (Must be alphanumeric.)")
            def check2(message : discord.Message) -> bool: 
                return message.author == ctx.author and message.channel.id == ctx.channel.id
            try:
                message = await self.bot.wait_for('message', timeout = 30, check = check2)
            except asyncio.TimeoutError: 
                return await ctx.edit("")            
            # This will be executed if the author responded properly
            else:
                name = message.content
                if not name.isalnum():
                    return await ctx.send("New name must be alphanumeric. (A-Z, 0-9)")
                
                name = name.upper()
                msg = await ctx.send(f"Old stock name: {playerstock[1]}\nNew Stock name: {name}\n**Are you sure you want to rename this stock for $100?**")
                
                def check3(reaction, user):
                    return user == ctx.author and str(reaction.emoji) == '✅'
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=30, check=check3)
                except asyncio.TimeoutError:
                    pass
                else:
                    try:
                        await ctx.reply('👍')
                    except:
                        await ctx.send('👍')
                    await self.bot.db.execute("UPDATE e_stocks SET ",(name, ctx.author.id,))
            
    @commands.group(invoke_without_command=True)
    async def invest(self, ctx, name_or_id, amount):
        """The base command for investments.
        Invoking `invest` without a subcommand allows you to invest in stocks."""
        player = await Player.get(ctx.author.id, self.bot)
        player.validate_bet(amount)
        stock = await self.bot.get_stock(name_or_id)
        if stock is None:
            await ctx.send("I couldn't find that stock. Double check the name/ID.")
            return
            
        cur = await self.bot.db.execute("SELECT * FROM e_invests WHERE stockid = ? AND userid = ?",(stock[0],ctx.author.id,))
        investment = await cur.fetchone()
        if investment is not None:
            await ctx.send("You're already invested in this stock.")
            return
        # Getting the stock again and updating it first prevents it from being exploited. lets do that
        cur = await self.bot.db.execute("SELECT * FROM e_stocks WHERE stockid = ?",(name_or_id,))
        stock = await cur.fetchone()
        if stock is None:
            name_or_id = name_or_id.upper()
            cur = await self.bot.db.execute("SELECT * FROM e_stocks WHERE name = ?",(name_or_id,))
            stock = await cur.fetchone()
        am = random.uniform(0.1,0.5)
        am = round(am,2)
        await self.bot.db.execute("UPDATE e_stocks SET points = (points + ?) WHERE stockid = ?",(am, name_or_id,))
        await self.bot.db.execute("UPDATE e_stocks SET points = (points + ?) WHERE name = ?",(am, name_or_id,))
        #(stockid int, userid int, invested double, stockname text, invested_at double, invested_date blob)
        rn = discord.utils.utcnow()
        await self.bot.db.execute("INSERT INTO e_invests VALUES (?, ?, ?, ?, ?, ?)",(stock[0], ctx.author.id, amount, stock[1], stock[2],rn,))
        await self.bot.db.execute("UPDATE e_users SET bal = (bal - ?) WHERE id = ?",(amount,ctx.author.id,))
        await ctx.send(f"Invested ${amount} in **{stock[1]}** at {round(stock[2], 2)} points!")
        
    @invest.command(invoke_without_command=True, description="Sells an investment.\nThe money you earn back is calculated like this: `money_to_pay = (current_stock_points - points_at_investment) * amount_invested`")
    async def sell(self, ctx, name_or_id):
        name_or_id = name_or_id.upper()
        player = await Player.get(ctx.author.id, self.bot)
        cur = await self.bot.db.execute("SELECT * FROM e_invests WHERE stockname = ? AND userid = ?",(name_or_id,ctx.author.id,))
        investment = await cur.fetchone()
        if investment is None:
            cur = await self.bot.db.execute("SELECT * FROM e_invests WHERE stockid = ? AND userid = ?",(name_or_id,ctx.author.id,))
            investment = await cur.fetchone()
            if investment is None:
                return await ctx.send("I couldn't find that stock, or you're not invested in it. Double check the name or ID.")
            
        c = await self.bot.db.execute("SELECT * FROM e_stocks WHERE stockid = ?",(investment[0],))
        stock = await c.fetchone()
        if stock is None:
            await ctx.send(f"This stock no longer exists. You will be refunded ${investment[2]} (the money you invested).")
            await self.bot.db.execute("UPDATE e_users SET bal = (bal + ?) WHERE id = ?",(investment[2],))
            await self.bot.db.execute("DELETE FROM e_invests WHERE stockname = ? AND userid = ?",(name_or_id, ctx.author.id,))
            await self.bot.db.execute("DELETE FROM e_invests WHERE stockid = ? AND userid = ?",(name_or_id, ctx.author.id,))
            return
        points_at_investment = round(investment[4],2)
        current_stock_points = round(stock[2],2)
        amount_invested = int(investment[2])
        money_to_pay = (current_stock_points - points_at_investment) * amount_invested
        money_to_pay = int(money_to_pay)
        if money_to_pay > 0:
            summary = f"${money_to_pay} will be depositied into your account.\nYou invested ${round(amount_invested,2)}, at {points_at_investment} points. The current points is {current_stock_points}"
        else:
            summary = f"${money_to_pay} will be taken from your account.\nYou invested ${amount_invested}, at {points_at_investment} points. The current points is {current_stock_points}."
        if (money_to_pay - amount_invested) > 0:
            summary += (f"\nThis is a net **profit** of ${(money_to_pay - amount_invested)}\n**Are you sure you want to sell your investment?**")
        elif (money_to_pay - amount_invested) < 0:
            gross_bal = (player.bal + (money_to_pay - amount_invested))
            if gross_bal < 0:
                return await ctx.send(f"You cannot sell this investment, because it would put you into debt (${(gross_bal)}). Try again later when the stock has higher points.")
            summary += (f"\nThis is a net **loss** of ${(money_to_pay - amount_invested)}\n**Are you sure you want to sell your investment?**")
        else:
            summary += (f"\nYou are essentially being refunded, as the amount you are getting paid is the same you invested.\n**Are you sure you want to sell your investment?**")
        msg = await ctx.send(summary)
        sellornot = await self.bot.prompt(ctx.author.id, msg, timeout=30)
        if not sellornot:
            await ctx.send("Cancelled, your investment was not sold.")
        else:
            am = random.uniform(0.1,0.5)
            am = round(am,2)
            await self.bot.db.execute("UPDATE e_stocks SET points = (points - ?) WHERE stockid = ?",(am, name_or_id,))
            await self.bot.db.execute("UPDATE e_stocks SET points = (points - ?) WHERE name = ?",(am, name_or_id,))
            await self.bot.db.execute("UPDATE e_users SET bal = (bal + ?) WHERE id = ?",(money_to_pay, ctx.author.id,))
            await self.bot.db.execute("DELETE FROM e_invests WHERE userid = ? AND stockid = ?",(ctx.author.id, name_or_id,))
            await self.bot.db.execute("DELETE FROM e_invests WHERE userid = ? AND stockname = ?",(ctx.author.id, name_or_id,))
            try: await ctx.reply('👍')
            except: await ctx.send('👍')     
        for r in msg.reactions: 
            try:await r.remove()
            except: pass
        await self.bot.db.commit()
        
async def setup(bot):
    await bot.add_cog(stocks(bot))
