import logging.handlers
import json
import traceback
import math
import pytz

import globals
import utils
from classes import Action
from classes import QuarterType

log = logging.getLogger("bot")


def getLinkToThread(threadID):
	return globals.SUBREDDIT_LINK + threadID


PUBLIC_ENUMS = {
	'Action': Action
}


class EnumEncoder(json.JSONEncoder):
	def default(self, obj):
		for enum in PUBLIC_ENUMS.values():
			if type(obj) is enum:
				return {"__enum__": str(obj)}
		return json.JSONEncoder.default(self, obj)


def as_enum(d):
	if "__enum__" in d:
		name, member = d["__enum__"].split(".")
		return getattr(PUBLIC_ENUMS[name], member)
	else:
		return d


def embedTableInMessage(message, table):
	if table is None:
		return message
	else:
		return "{}{}{})".format(message, globals.datatag, json.dumps(table, cls=EnumEncoder).replace(" ", "%20"))


def extractTableFromMessage(message):
	datatagLocation = message.find(globals.datatag)
	if datatagLocation == -1:
		return None
	data = message[datatagLocation + len(globals.datatag):-1].replace("%20", " ")
	try:
		table = json.loads(data, object_hook=as_enum)
		return table
	except Exception:
		log.debug(traceback.format_exc())
		return None


markdown = [
	{'value': "[", 'result': "%5B"},
	{'value': "]", 'result': "%5D"},
	{'value': "(", 'result': "%28"},
	{'value': ")", 'result': "%29"},
]


def escapeMarkdown(value):
	for replacement in markdown:
		value = value.replace(replacement['value'], replacement['result'])
	return value


def unescapeMarkdown(value):
	for replacement in markdown:
		value = value.replace(replacement['result'], replacement['value'])
	return value


def flair(team):
	return "[{}](#f/{})".format(team.name, team.tag)


def renderTime(time):
	if time < 0:
		return "0:00"
	else:
		return "{}:{}".format(str(math.trunc(time / 60)), str(time % 60).zfill(2))


def renderBallLocation(game, useFlair):
	if game.status.location < 50:
		if useFlair:
			return "{} {}".format(str(game.status.location), flair(game.team(game.status.possession)))
		else:
			return "{} {}".format(game.team(game.status.possession).name, str(game.status.location))
	elif game.status.location > 50:
		if useFlair:
			return "{} {}".format(str(100 - game.status.location), flair(game.team(game.status.possession.negate())))
		else:
			return "{} {}".format(game.team(game.status.possession.negate()).name, str(100 - game.status.location))
	else:
		return str(game.status.location)


def renderGame(game):
	bldr = []

	bldr.append(flair(game.away))
	bldr.append(" **")
	bldr.append(game.away.name)
	bldr.append("** @ ")
	bldr.append(flair(game.home))
	bldr.append(" **")
	bldr.append(game.home.name)
	bldr.append("**\n\n")

	if game.startTime is not None:
		bldr.append(" **Game Start Time:** ")
		bldr.append(unescapeMarkdown(game.startTime))
		bldr.append("\n\n")

	if game.location is not None:
		bldr.append(" **Location:** ")
		bldr.append(unescapeMarkdown(game.location))
		bldr.append("\n\n")

	if game.station is not None:
		bldr.append(" **Watch:** ")
		bldr.append(unescapeMarkdown(game.station))
		bldr.append("\n\n")

	bldr.append("\n\n")

	for homeAway in [False, True]:
		bldr.append(flair(game.team(homeAway)))
		bldr.append("\n\n")
		bldr.append(
			"Total Passing Yards|Total Rushing Yards|Total Yards|Interceptions Lost|Fumbles Lost|Field Goals|Time of Possession|Timeouts\n")
		bldr.append(":-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:\n")
		bldr.append("{} yards|{} yards|{} yards|{}|{}|{}/{}|{}|{}".format(
			game.status.stats(homeAway).yardsPassing,
			game.status.stats(homeAway).yardsRushing,
			game.status.stats(homeAway).yardsTotal,
			game.status.stats(homeAway).turnoverInterceptions,
			game.status.stats(homeAway).turnoverFumble,
			game.status.stats(homeAway).fieldGoalsScored,
			game.status.stats(homeAway).fieldGoalsAttempted,
			renderTime(game.status.stats(homeAway).posTime),
			game.status.state(homeAway).timeouts
		)
		)
		bldr.append("\n\n___\n")

	bldr.append("Game Summary|Time\n")
	bldr.append(":-:|:-:\n")
	for drive in []:
		bldr.append("test|test\n")

	bldr.append("\n___\n\n")

	bldr.append("Clock|Quarter|Down|Ball Location|Possession|Playclock|Deadline\n")
	bldr.append(":-:|:-:|:-:|:-:|:-:|:-:|:-:\n")
	bldr.append(renderTime(game.status.clock))
	bldr.append("|")
	bldr.append(str(game.status.quarter))
	bldr.append("|")
	bldr.append(getDownString(game.status.down))
	bldr.append(" & ")
	bldr.append(str(game.status.yards))
	bldr.append("|")
	bldr.append(renderBallLocation(game, True))
	bldr.append("|")
	bldr.append(flair(game.team(game.status.possession)))
	bldr.append("|")
	bldr.append(renderDatetime(game.playclock))
	bldr.append("|")
	bldr.append(renderDatetime(game.deadline))

	bldr.append("\n\n___\n\n")

	bldr.append("Team|")
	numQuarters = max(len(game.status.homeState.quarters), len(game.status.awayState.quarters))
	for i in range(numQuarters):
		bldr.append("Q")
		bldr.append(str(i + 1))
		bldr.append("|")
	bldr.append("Total\n")
	bldr.append((":-:|" * (numQuarters + 2))[:-1])
	bldr.append("\n")
	for homeAway in [True, False]:
		bldr.append(flair(game.team(homeAway)))
		bldr.append("|")
		for quarter in game.status.state(homeAway).quarters:
			bldr.append(str(quarter))
			bldr.append("|")
		bldr.append("**")
		bldr.append(str(game.status.state(homeAway).points))
		bldr.append("**\n")

	if game.forceChew:
		bldr.append("\n#This game is in default chew the clock mode.\n")

	if game.status.waitingId != "":
		bldr.append("\nWaiting on a response from {} to this {}.\n"
					.format(
						getCoachString(game, game.status.waitingOn),
						getLinkFromGameThing(game.thread, utils.getPrimaryWaitingId(game.status.waitingId))))


	if game.status.quarterType == QuarterType.END:
		bldr.append("\n#Game complete, {} wins!\n".format(game.status.winner))

	return ''.join(bldr)


def renderPostGame(game):
	bldr = []

	bldr.append(flair(game.away))
	bldr.append(" **")
	bldr.append(game.away.name)
	bldr.append("** @ ")
	bldr.append(flair(game.home))
	bldr.append(" **")
	bldr.append(game.home.name)
	bldr.append("**\n\n")

	if game.startTime is not None:
		bldr.append(" **Game Start Time:** ")
		bldr.append(unescapeMarkdown(game.startTime))
		bldr.append("\n\n")

	if game.location is not None:
		bldr.append(" **Location:** ")
		bldr.append(unescapeMarkdown(game.location))
		bldr.append("\n\n")

	if game.station is not None:
		bldr.append(" **Watch:** ")
		bldr.append(unescapeMarkdown(game.station))
		bldr.append("\n\n")

	bldr.append("\n\n")

	for homeAway in [False, True]:
		bldr.append(flair(game.team(homeAway)))
		bldr.append("\n\n")
		bldr.append(
			"Total Passing Yards|Total Rushing Yards|Total Yards|Interceptions Lost|Fumbles Lost|Field Goals|Time of Possession|Timeouts\n")
		bldr.append(":-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:\n")
		bldr.append("{} yards|{} yards|{} yards|{}|{}|{}/{}|{}|{}".format(
			game.status.stats(homeAway).yardsPassing,
			game.status.stats(homeAway).yardsRushing,
			game.status.stats(homeAway).yardsTotal,
			game.status.stats(homeAway).turnoverInterceptions,
			game.status.stats(homeAway).turnoverFumble,
			game.status.stats(homeAway).fieldGoalsScored,
			game.status.stats(homeAway).fieldGoalsAttempted,
			renderTime(game.status.stats(homeAway).posTime),
			game.status.state(homeAway).timeouts
		)
		)
		bldr.append("\n\n___\n")

	bldr.append("Team|")
	numQuarters = max(len(game.status.homeState.quarters), len(game.status.awayState.quarters))
	for i in range(numQuarters):
		bldr.append("Q")
		bldr.append(str(i + 1))
		bldr.append("|")
	bldr.append("Total\n")
	bldr.append((":-:|" * (numQuarters + 2))[:-1])
	bldr.append("\n")
	for homeAway in [True, False]:
		bldr.append(flair(game.team(homeAway)))
		bldr.append("|")
		for quarter in game.status.state(homeAway).quarters:
			bldr.append(str(quarter))
			bldr.append("|")
		bldr.append("**")
		bldr.append(str(game.status.state(homeAway).points))
		bldr.append("**\n")

	playBldr = []
	for play in game.status.plays:
		playBldr.append(str(play))
	playString = '\n'.join(playBldr)
	pasteOutput = utils.paste("Thread summary", ''.join(playString)).decode('utf-8')

	bldr.append("\n")
	if "pastebin.com" in pasteOutput:
		log.debug("Finished pasting: {}".format(pasteOutput))
		bldr.append("[Plays](")
		bldr.append(pasteOutput)
		bldr.append(")\n")
	else:
		bldr.append("Unable to generate play list\n")

	bldr.append("\n")
	bldr.append("#Game complete, {} wins!".format(game.status.winner))

	return ''.join(bldr)


def getLinkFromGameThing(threadId, thingId):
	if thingId.startswith("t1"):
		waitingMessageType = "comment"
		link = "{}/_/{}".format(getLinkToThread(threadId), thingId[3:])
	elif thingId.startswith("t4"):
		waitingMessageType = "message"
		link = "{}{}".format(globals.MESSAGE_LINK, thingId[3:])
	else:
		return "Something went wrong. Not valid thingid: {}".format(thingId)

	return "[{}]({})".format(waitingMessageType, link)


def getCoachString(game, isHome):
	bldr = []
	for coach in game.team(isHome).coaches:
		bldr.append("/u/{}".format(coach))
	return " and ".join(bldr)


def getNthWord(number):
	if number == 1:
		return "1st"
	elif number == 2:
		return "2nd"
	elif number == 3:
		return "3rd"
	elif number == 4:
		return "4th"
	else:
		return "{}th".format(number)


def getDownString(down):
	if down >= 1 and down <= 4:
		return getNthWord(down)
	else:
		log.warning("Hit a bad down number: {}".format(down))
		return "{}".format(down)


def getLocationString(game):
	location = game.status.location
	offenseTeam = game.team(game.status.possession).name
	defenseTeam = game.team(game.status.possession.negate()).name
	if location <= 0 or location >= 100:
		log.warning("Bad location: {}".format(location))
		return str(location)

	if location == 0:
		return "{} goal line".format(offenseTeam)
	if location < 50:
		return "{} {}".format(offenseTeam, location)
	elif location == 50:
		return str(location)
	else:
		return "{} {}".format(defenseTeam, 100 - location)


def getCurrentPlayString(game):
	bldr = []
	if game.status.waitingAction == Action.CONVERSION:
		bldr.append("{} just scored. ".format(game.team(game.status.possession).name))
	elif game.status.waitingAction == Action.KICKOFF:
		bldr.append("{} is kicking off. ".format(game.team(game.status.possession).name))
	else:
		bldr.append("It's {} and {} on the {}. ".format(
			getDownString(game.status.down),
			"goal" if game.status.location + game.status.yards >= 100 else game.status.yards,
			getLocationString(game)
		))

	if utils.isGameOvertime(game):
		bldr.append("In the {}.".format(getNthWord(game.status.quarter)))
	else:
		bldr.append("{} left in the {}.".format(renderTime(game.status.clock), getNthWord(game.status.quarter)))

	return ''.join(bldr)


def getWaitingOnString(game):
	string = "Error, no action"
	if game.status.waitingAction == Action.COIN:
		string = "Waiting on {} for coin toss".format(game.team(game.status.waitingOn).name)
	elif game.status.waitingAction == Action.DEFER:
		string = "Waiting on {} for receive/defer".format(game.team(game.status.waitingOn).name)
	elif game.status.waitingAction == Action.KICKOFF:
		string = "Waiting on {} for kickoff number".format(game.team(game.status.waitingOn).name)
	elif game.status.waitingAction == Action.PLAY:
		if game.status.waitingOn == game.status.possession:
			string = "Waiting on {} for an offensive play".format(game.team(game.status.waitingOn).name)
		else:
			string = "Waiting on {} for a defensive number".format(game.team(game.status.waitingOn).name)

	return string


def listSuggestedPlays(game):
	if game.status.waitingAction == Action.CONVERSION:
		return "**PAT** or **two point**"
	elif game.status.waitingAction == Action.KICKOFF:
		return "**normal**, **squib** or **onside**"
	else:
		if game.status.down == 4:
			if game.status.location > 62:
				return "**field goal**, or go for it with **run** or **pass**"
			elif game.status.location > 57:
				return "**punt** or **field goal**, or go for it with **run** or **pass**"
			else:
				return "**punt**, or go for it with **run** or **pass**"
		else:
			return "**run** or **pass**"


def buildMessageLink(recipient, subject, content):
	return "https://np.reddit.com/message/compose/?to={}&subject={}&message={}".format(
		recipient,
		subject.replace(" ", "%20"),
		content.replace(" ", "%20")
	)


def renderDatetime(dtTm, includeLink=True):
	localized = pytz.utc.localize(dtTm).astimezone(globals.EASTERN)
	timeString = localized.strftime("%m/%d %I:%M %p EST")
	if not includeLink:
		return timeString
	base = "https://www.timeanddate.com/countdown/afootball?p0=0&msg=Playclock&iso="
	return "[{}]({}{})".format(timeString, base, dtTm.strftime("%Y%m%dT%H%M%S"))


def renderGameStatusMessage(game):
	bldr = []
	bldr.append("[Game](")
	bldr.append(globals.SUBREDDIT_LINK)
	bldr.append(game.thread)
	bldr.append(") status.\n\n")

	bldr.append(getCoachString(game, False))
	bldr.append(" as ")
	bldr.append(game.team(False).name)
	bldr.append("/away")
	bldr.append(" vs ")
	bldr.append(getCoachString(game, True))
	bldr.append(" as ")
	bldr.append(game.team(True).name)
	bldr.append("/home")
	bldr.append("\n\n")

	bldr.append("Status|Waiting|Link\n")
	bldr.append(":-:|:-:|:-:\n")

	for i, status in enumerate(game.previousStatus):
		bldr.append(game.team(status.possession).name)
		bldr.append("/")
		bldr.append(status.possession.name())
		bldr.append(" with ")
		bldr.append(getNthWord(status.down))
		bldr.append(" & ")
		bldr.append(str(status.yards))
		bldr.append(" on the ")
		bldr.append(str(status.location))
		bldr.append(" with ")
		bldr.append(renderTime(status.clock))
		bldr.append(" in the ")
		bldr.append(getNthWord(status.quarter))
		bldr.append("|")
		primaryWaitingId = utils.getPrimaryWaitingId(status.waitingId)
		bldr.append(getLinkFromGameThing(game.thread, primaryWaitingId))
		bldr.append(" ")
		bldr.append(status.waitingOn.name())
		bldr.append("/")
		bldr.append(game.team(status.waitingOn).name)
		bldr.append(" for ")
		bldr.append(status.waitingAction.name)
		bldr.append("|")
		bldr.append("[Message](")
		bldr.append(buildMessageLink(
			globals.ACCOUNT_NAME,
			"Kick game",
			"kick {} revert:{} message:{}".format(game.thread, i, status.messageId)
		))
		bldr.append(")\n")

	return ''.join(bldr)