from datetime import datetime, timedelta, time
import time
from pathlib import Path
from core.base.model.AliceSkill import AliceSkill
from core.base.model.Intent import Intent
from core.dialog.model.DialogSession import DialogSession
from core.util.Decorators import IntentHandler
from core.base.SuperManager import SuperManager


class Reminder(AliceSkill):

	"""
	Author: LazzaAU. This skill utilises these main methods for functional operation
		- addReminder initiates the reminder process between user and Alice
		- Then passes onto processTheSpecifiedTime() for processing of the time
		- then onto maincode() for finalising the timer
			Amongst that process there are methods for converting spoken times to epoch and back to human time
			and Various other functions and checks, delete, how long left, etc
			Also one main Method which allows switching between the three events (Reminder/Timer/Alarm) is the
		- setEventType() method. This allows the skill to determine what of the 3 events we are dealing with
	"""
	_REMINDERDBNAME = 'MyReminders'
	_TIMERDBNAME = 'MyTimer'
	_ALARMDBNAME = 'MyAlarm'
	_DATABASE = {
		_REMINDERDBNAME: [
			'internalId TEXT NOT NULL',
			'message TEXT NOT NULL',
			'timestamp INTEGER NOT NULL',
			'SiteID TEXT NOT NULL',
			'EventType TEXT NOT NULL'
		],
		_TIMERDBNAME   : [
			'internalId TEXT NOT NULL',
			'message TEXT NOT NULL',
			'timestamp INTEGER NOT NULL',
			'SiteID TEXT NOT NULL',
			'EventType TEXT NOT NULL'
		],
		_ALARMDBNAME   : [
			'internalId TEXT NOT NULL',
			'message TEXT NOT NULL',
			'timestamp INTEGER NOT NULL',
			'SiteID TEXT NOT NULL',
			'EventType TEXT NOT NULL'
		]
	}
	_INTENT_ADD_REMINDER = Intent('ReminderEvent')
	_INTENT_ADD_DATE = Intent('ReminderTime', isProtected=True)
	_INTENT_ADD_MESSAGE = Intent('ReminderMessage', isProtected=True)
	_INTENT_ANSWER_YES_OR_NO = Intent('AnswerYesOrNo', isProtected=True)
	_INTENT_TIME_REMAINING = Intent('ReminderRemaining', isProtected=True)
	_INTENT_SELECT_ITEM = Intent('ChooseListItem', isProtected=True)
	_INTENT_DELETE_REMINDER = Intent('ReminderDelete', isProtected=True)


	def __init__(self):

		self._spokenDuration = ''
		self._dateTimeStr = ''
		self._dateTimeObject = ''
		self._secondsDuration = ''
		self._reminderMessage = ''
		self._dbId = 0
		self._theSiteId = 'default'
		self._dbTableValues = []
		self._selectedMessages = None
		self._dbTimeStampList = []
		self._dbMessageList = []
		self._dbRowIdList = []
		self._dbSiteList = []
		self._eventType = ''
		self._activeDataBase = 'MyReminders'
		self._dataBaseList = ['MyReminders', 'MyTimer', 'MyAlarm']
		self._TimerEventType = []

		self._INTENTS = [
			self._INTENT_ANSWER_YES_OR_NO,
			self._INTENT_ADD_DATE,
			self._INTENT_ADD_MESSAGE,
			self._INTENT_SELECT_ITEM,
			(self._INTENT_ADD_REMINDER, self.addReminder)
		]

		# init Dialog mapping to prevent dialog clashing with other skills
		self._INTENT_ANSWER_YES_OR_NO.dialogMapping = {
			'ConfirmIfDeletingAllMessages': self.actionFromYesNoAnswer,
			# 'ConfirmIfMessageAndTimeCorrect': self.processTheSpecifiedTime

		}
		self._INTENT_ADD_REMINDER.dialogMapping = {
			'AddMessageToReminder': self.processTheSpecifiedTime
		}

		self._INTENT_ADD_DATE.dialogMapping = {
			# 'AddedTheDateOrDuration': self.addMessageToReminder

		}

		self._INTENT_DELETE_REMINDER.dialogMapping = {
			'DeleteSomeReminder': self.deleteRequestedReminder
		}

		self._INTENT_SELECT_ITEM.dialogMapping = {
			'SelectedItemFromList': self.extractRequestedItemFromList,
			'askWhatItemFromList' : self.extractRequestedItemFromList
		}

		super().__init__(self._INTENTS, databaseSchema=self._DATABASE)


	# Cleanup the Db on boot up
	def onStart(self):
		super().onStart()
		self.logInfo(f'Doing database maintenance for the Reminder skill')
		self.cleanupDeadTimers()
		self.onFiveMinute()


	# This is called directly by the mapping for intents because DURATION was specified
	def addReminder(self, session: DialogSession):
		self.setEventType(session)
		self.logDebug(f'Slots = {session.slots}')

		# If theres no reminder date or duration specified then ask for a message
		if self._eventType + 'DateAndTime' in session.slots or 'Duration' in session.slots:
			self.continueDialog(
				sessionId=session.sessionId,
				text=self.randomTalk(text='respondReminderMessage', replace=[self._eventType]),
				intentFilter=[self._INTENT_ADD_MESSAGE],
				currentDialogState='AddMessageToReminder',
				slot='ReminderMessage'
			)
			return
		else:
			if self._eventType + 'DateAndTime' not in session.slots or 'Duration' not in session.slots:
				self.continueDialog(
					sessionId=session.sessionId,
					text=self.randomTalk(text='respondSetDuration', replace=[self._eventType]),
					intentFilter=[self._INTENT_ADD_DATE],
					currentDialogState='AddedTheDateOrDuration',
					slot='ReminderDateAndTime'
				)
				return


	def processTheSpecifiedTime(self, session: DialogSession):
		if self._eventType + 'DateAndTime' in session.slotsAsObjects:

			self._spokenDuration = session.slotValue(self._eventType + 'DateAndTime', ).split()  # returns format [2020-04-08, 10:25:00, +10]
			del self._spokenDuration[-1]  # Removes the timezone off the end
			self._dateTimeStr = " ".join(self._spokenDuration)  # converts the list to a string
			self._dateTimeObject = datetime.strptime(self._dateTimeStr, '%Y-%m-%d %H:%M:%S')
			self._secondsDuration = self._dateTimeObject - datetime.today()  # find the difference between requested time and now

		if 'Duration' in session.slotsAsObjects:
			self._secondsDuration = self.Commons.getDuration(session)  # Gets the requested duration in seconds

		self._reminderMessage = session.slotRawValue('ReminderMessage')  # set the reminder message

		if self._eventType + 'DateAndTime' in session.slotsAsObjects:  # Convert to Seconds if its called with DateAndTime slot
			secs = round(self._secondsDuration.total_seconds())
		else:
			secs = self._secondsDuration  # Seconds are already converted so set the secs var

		if 'Food' in session.slots:
			self.setFoodTimer(session, secs)

		else:
			self.processAndStoreReminder(session, secs)


	# This does the actual setting of the timer details and storing to Db
	def processAndStoreReminder(self, session: DialogSession, secs):

		self.logDebug(f'The requested time converted to seconds is {secs}')
		secondsToFloat = float(secs)

		# count of the amount of rows in the Database
		myTablecount = self.tableRowCount()

		# Convert to Epoch timestamp in Seconds for storing in Db
		timeStampForDb = self.createEpochTimeStamp(secs)

		# VocalSeconds is used to give Alice's reply a human friendly responce
		vocalSeconds = str(timedelta(seconds=secs))

		# Set event type for later recall from db when dofiveMinute is called after a reboot
		self._TimerEventType = self._eventType

		if secondsToFloat < 298:
			self.ThreadManager.doLater(
				interval=secondsToFloat,
				func=self.runReminder,
				args=[self._eventType, self._reminderMessage]

			)

		# Alice Confirming that the Reminder has been set ..........................................................
		self.endDialog(sessionId=session.sessionId, text=self.randomTalk('respondConfirmed', replace=[self._eventType, self._reminderMessage, vocalSeconds]))

		# write Timer info to the database or not depending on length of time (saves double up reminder from onFive trigger
		try:
			if secondsToFloat >= 299:
				self.databaseInsert(
					tableName=self._activeDataBase,
					values={'internalID': myTablecount + 1, 'message': self._reminderMessage, 'timestamp': timeStampForDb, 'SiteID': self._theSiteId, 'EventType': self._eventType}
				)
		except:
			self.logError(f'Failed to enable timer due to **Database** temporarily being locked')


	# Respond with The Reminder once time is finished,
	def runReminder(self, event, Message):
		self.reminderSound(event)
		time.sleep(0.5)
		self.say(self.randomTalk(text='respondReminder', replace=[event, Message]), siteId=self._theSiteId)
		time.sleep(0.5)
		self.cleanupDeadTimers()


	def foodReminder(self):
		self.say(self.randomTalk(text='respondFoodTimer'), siteId=self._theSiteId)


	# required
	@staticmethod
	def createEpochTimeStamp(seconds):
		timeStampForDatabase = datetime.now() + timedelta(seconds=seconds)
		date_time = str(timeStampForDatabase)
		pattern = '%Y-%m-%d %H:%M:%S.%f'
		epoch = int(time.mktime(time.strptime(date_time, pattern)))
		return epoch


	# sets a mid timer, timer to alert to go check the food
	def setFoodTimer(self, session: DialogSession, secs):
		checkTheFoodTimer = secs / 2
		self.ThreadManager.doLater(
			interval=checkTheFoodTimer,
			func=self.foodReminder
		)
		self.processAndStoreReminder(session, secs)



	def askIfTheDetailsAreCorrect(self, session: DialogSession, secs = None):

		self._reminderMessage = session.slotRawValue('ReminderMessage')
		SpecifiedTime = time.strftime('%H:%M:%S', time.gmtime(secs))
		# Disabled confirmation code for setting a reminder... was bit over the top
		# but left it here incase of user request (removed A from addMessageToReminder
		if 'ddMessageToReminder' in session.currentState:
			self.continueDialog(
				sessionId=session.sessionId,
				text=f'ok this is what i heard. You would like a {self._eventType} set for {SpecifiedTime} with a topic of {self._reminderMessage}. Is that correct ?',
				intentFilter=[self._INTENT_ANSWER_YES_OR_NO],
				previousIntent='AddMessageToReminder',
				currentDialogState='ConfirmIfMessageAndTimeCorrect',
				probabilityThreshold=0.1
			)
			return secs

		elif 'ReminderDeleteAll' in session.slots:
			self.continueDialog(
				sessionId=session.sessionId,
				text=f'Are you sure you want to delete all of your {self._eventType} ?',
				intentFilter=[self._INTENT_ANSWER_YES_OR_NO],
				currentDialogState='ConfirmIfDeletingAllMessages',
				probabilityThreshold=0.1
			)


	# do something in responce to a yes or no reply
	def actionFromYesNoAnswer(self, session: DialogSession, secs = None):

		if 'ConfirmIfMessageAndTimeCorrect' in session.currentState:
			if self.Commons.isYes(session):
				self.processAndStoreReminder(session, secs)
			else:
				self.endDialog(
					sessionId=session.sessionId,
					text=f'Ok i won\'t continue with the {self._eventType} please try again'
				)
		elif 'ConfirmIfDeletingAllMessages' in session.currentState:

			if self.Commons.isYes(session):
				self.deleteRequestedReminder(session)
			else:
				self.endDialog(
					sessionId=session.sessionId,
					text=self.randomTalk('respondToANoReply', replace=[self._eventType]),
				)


	# This returns the amount of rows in the database table
	def tableRowCount(self):

		for dbRow in self.databaseFetch(
				tableName=self._activeDataBase,
				query='SELECT count (*) FROM :__table__',
				values={},
				method='all'
		):
			return dbRow[0]


	# This updates the internalID value to match table rowid
	def updateInternalIdNumberOfDb(self):
		s = 0
		while s <= len(self._dataBaseList) - 1:
			if s == 0:
				self._eventType = 'Reminder'
				self._activeDataBase = self._REMINDERDBNAME
			elif s == 1:
				self._eventType = 'Timer'
				self._activeDataBase = self._TIMERDBNAME
			else:
				self._eventType = 'Alarm'
				self._activeDataBase = self._ALARMDBNAME
			self.viewTableValues()

			try:
				self.DatabaseManager.update(
					tableName=self._activeDataBase,
					callerName=self.name,
					values={},
					query='UPDATE :__table__ SET internalId = rowid'
				)
			except:

				self.ThreadManager.doLater(
					interval=300.0,
					func=self.updateInternalIdNumberOfDb()
				)
			s += 1


	# This sets "self._dbTableValues" to a list of all current Database table values
	def viewTableValues(self):

		# self.updateInternalIdNumberOfDb()  # resets internalId column to rowid value
		remTableList = []
		for row in self.databaseFetch(
				tableName=self._activeDataBase,
				query='SELECT * FROM :__table__ ',
				values={},
				method='all'
		):
			if tuple(row):
				if remTableList is None:
					remTableList = list(tuple(row))
				else:
					remTableList.append(list(tuple(row)))

		self._dbTableValues = remTableList  # Get the entire Reminder Database table
		self._dbSiteList = [x[3] for x in self._dbTableValues]  # get list of SiteId for use on a Alice restart
		self._dbTimeStampList = [x[2] for x in self._dbTableValues]  # get list of TimeStamps
		self._dbMessageList = [x[1] for x in self._dbTableValues]  # get the list of messages
		self._dbRowIdList = [x[0] for x in self._dbTableValues]  # get The list of row ID's
		self._TimerEventType = [x[4] for x in self._dbTableValues]  # get event type from db
		return


	# Returns the remaining time left on a choosen timer
	def getTimeRemaining(self, session: DialogSession):
		convertedTime = self.convertEpochMinusNowToHumanReadableTime()

		self.endDialog(
			sessionId=session.sessionId,
			text=f'there is {convertedTime} left on that {self._eventType}',
			siteId=session.siteId
		)


	# This starts the process of asking user what item to look up in the list
	def getItemFromList(self, session: DialogSession):
		messageInt = len(self._dbMessageList)  # Find the amount of messages and subtract 1
		if messageInt > 8:
			self.endDialog(
				sessionId=session.sessionId,
				text=self.randomTalk('respondHighMessageLength', replace=[self._eventType])
			)
		messageInt = str(messageInt)  # convert the int to a string for joining
		textFilePointer = 'respondReminder' + messageInt
		textFilePointer = str(textFilePointer)  # textFilePointer is used to append a number of messages to correspond to the talk file {}

		if len(self._dbMessageList) == 0:
			self.endDialog(
				sessionId=session.sessionId,
				text=f'You have no active {self._eventType}, zip, ziltch, nada'
			)
			return
		elif len(self._dbMessageList) == 1:
			self._selectedMessages = self._dbMessageList[0]

			if 'ReminderDeleteAll' in session.slotsAsObjects or 'ReminderDelete' in session.slotsAsObjects:

				self.deleteRequestedReminder(session)

			elif self._eventType + 'RemainingTime' in session.slotsAsObjects:
				self.getTimeRemaining(session)
			elif self._eventType + 'Stop' in session.slotsAsObjects:
				self.userAskedToStopReminder(session)
			else:
				return
		else:
			self.askForWhichItems(session, textFilePointer, self._dbMessageList)


	# This is used for asking the user to select the item from a list and return it to extractRequestedItemFromList()
	def askForWhichItems(self, session: DialogSession, textFilePointer, dbMessageList):
		dbMessageList.insert(0, self._eventType)

		self.continueDialog(
			sessionId=session.sessionId,
			text=self.randomTalk(textFilePointer, replace=[message for message in self._dbMessageList]),
			intentFilter=[self._INTENT_SELECT_ITEM],
			currentDialogState='askWhatItemFromList',
			probabilityThreshold=0.1,
			slot='Number'
		)
		del dbMessageList[0]


	# This currently returns the selected number to extractRequestedItemFromList()
	def extractRequestedItemFromList(self, session: DialogSession):

		intent = session.intentName

		if intent == self._INTENT_SELECT_ITEM:
			if 'Number' in session.slotsAsObjects:

				if session.slotValue('Number') > len(self._dbMessageList):
					self.logWarning(f'That number appears to be invalid')
					self.getItemFromList(session)
					return

				itemChosen = session.slotValue('Number')
				itemChosen = int(itemChosen) - 1  # turn float into a int then subtract 1 for indexing the list
				self._selectedMessages = self._dbMessageList[itemChosen]  # extract the actual requested message

				if 'ReminderDelete' in session.slotsAsObjects:
					self.deleteRequestedReminder(session)

				elif self._eventType + 'RemainingTime' in session.slotsAsObjects:
					self.getTimeRemaining(session)

				elif self._eventType + 'Stop' in session.slotsAsObjects:
					self.userAskedToStopReminder(session)

			else:
				self.continueDialog(
					sessionId=session.sessionId,
					text=f'I didn\'t hear a number, please try again ',
					intentFilter=[self._INTENT_SELECT_ITEM],
					currentDialogState='askWhatItemFromList'
				)
		else:
			self.logWarning(f'The expected Intent was not received')


	def cleanupDeadTimers(self):
		s = 0

		while s <= len(self._dataBaseList) - 1:
			if s == 0:
				self._eventType = 'Reminder'
			elif s == 1:
				self._eventType = 'Timer'
			else:
				self._eventType = 'Alarm'
			self.viewTableValues()
			i = 0
			for x in self._dbTimeStampList:  # x = a individual timestamp from _dbTimeStampList

				epochTimeNow = datetime.now().timestamp()  # Returns the epoch time for right now

				if x < epochTimeNow:
					self.DatabaseManager.delete(
						tableName=self._dataBaseList[s],
						query='DELETE FROM :__table__ WHERE timestamp < :tmpTimestamp',
						values={'tmpTimestamp': epochTimeNow},
						callerName=self.name
					)
					i += 1
			if i > 0:
				self.viewTableValues()
				self.logDebug(f'Just deleted {i} redundant {self._eventType} from {self._dataBaseList[s]}')
			s += 1


	# confirmed that stop event works
	def userAskedToStopReminder(self, session: DialogSession):
		self.setEventType(session)

		self.DatabaseManager.delete(
			tableName=self._activeDataBase,
			query='DELETE FROM :__table__ WHERE message = :tmpMessage',
			values={'tmpMessage': self._selectedMessages},
			callerName=self.name)

		self.endDialog(
			sessionId=session.sessionId,
			text=self.randomTalk('respondDelete', replace=[self._eventType]),
			siteId=session.siteId
		)
		self.cleanupDeadTimers()

	# Used to Convert the Database Timestamp into seconds
	def convertEpochMinusNowToSeconds(self, epochSeconds = None):
		epochTimeNow = datetime.now().timestamp()  # Returns the epoch time for right now
		indexPos = 0
		i = 0

		if epochSeconds is not None:
			epoch2Seconds = (epochSeconds - epochTimeNow)
			return epoch2Seconds
		else:
			length = len(self._dbTableValues)
			while i < length:

				if self._selectedMessages in self._dbTableValues[i]:
					indexPos = i
					break
				i += 1

			timestampActual = self._dbTableValues[indexPos][2]
			differenceInSeconds = (timestampActual - epochTimeNow)

			return differenceInSeconds


	# Converts Epoch time from DB to a Human readable output
	def convertEpochMinusNowToHumanReadableTime(self):
		ConvertedToSeconds = self.convertEpochMinusNowToSeconds()

		return str(timedelta(seconds=round(ConvertedToSeconds)))


	# I believe this to be fully functional for now, deletes a Item from DB the cleans up the row id's
	def deleteRequestedReminder(self, session: DialogSession):
		self.setEventType(session)

		if 'ReminderDeleteAll' not in session.slots:

			self.DatabaseManager.delete(
				tableName=self._activeDataBase,
				query='DELETE FROM :__table__ WHERE message = :tmpMessage',
				values={'tmpMessage': self._selectedMessages},
				callerName=self.name)

			self.endDialog(
				sessionId=session.sessionId,
				text=self.randomTalk('respondDelete', replace=[self._eventType]),
				siteId=session.siteId,
			)

			self.logInfo(f'Successfully deleted the requested {self._eventType} from the database')
			return
		else:
			self.endDialog(
				sessionId=session.sessionId,
				text=self.randomTalk('respondDeleteAll', replace=[self._eventType]),
				siteId=session.siteId,
			)
			self.DatabaseManager.delete(
				tableName=self._activeDataBase,
				query='DELETE FROM :__table__ ',
				values={},
				callerName=self.name
			)
		self.cleanupDeadTimers()

	# This does a 5 minute check of the stored timers and if a timer is within 320 seconds of activating
	# then we initiate the actual timer thread
	def onFiveMinute(self):
		self.viewTableValues()
		s = 0

		while s <= len(self._dataBaseList) - 1:
			self._activeDataBase = self._dataBaseList[s]
			if 'MyReminder' in self._activeDataBase:
				self._eventType = 'Reminder'
			elif 'MyTimer' in self._activeDataBase:
				self._eventType = 'Timer'
			else:
				self._eventType = 'Alarm'

			self.viewTableValues()
			self.logDebug(f'Checking for active timers in {self._activeDataBase} database')

			for x in self._dbTableValues:
				TimerMessage = x[1]
				self._TimerEventType = x[4]
				theSeconds = x[2]
				convertedTime = self.convertEpochMinusNowToSeconds(theSeconds)
				float(convertedTime)
				vocalSeconds = str(timedelta(seconds=round(convertedTime)))
				self.logDebug(f'You have a {self._TimerEventType} with {vocalSeconds} left on it')

				if convertedTime < 260.0:
					self.ThreadManager.doLater(
						interval=convertedTime,
						func=self.runReminder,
						args=[self._TimerEventType, TimerMessage]
					)
					time.sleep(0.5)
					self.cleanupDeadTimers()
			s += 1


	def reminderSound(self, event):

		path = event
		if 'Reminder' in event:
			soundFile = 'fanfare2.wav'
		elif 'Timer' in event:
			soundFile = 'Timer.wav'
		else:
			soundFile = 'Alarm.wav'

		self.playSound(
			soundFilename=soundFile,
			location=Path(f'{SuperManager.getInstance().commons.rootDir()}/skills/Reminder/Sounds/{path}'),
			sessionId='ReminderTriggered',
			siteId=self._theSiteId
		)


	# Critical method for allowing reminder/timer/alarm to all play nicely together
	def setEventType(self, session: DialogSession):
		self._theSiteId = session.siteId

		if 'ReminderEvent' in session.slots or 'ReminderSlot' in session.slots or 'ReminderStop' in session.slots:
			self._eventType = 'Reminder'
			self._activeDataBase = self._REMINDERDBNAME
		elif 'TimerEvent' in session.slots or 'TimerSlot' in session.slots or 'TimerStop' in session.slots:
			self._eventType = 'Timer'
			self._activeDataBase = self._TIMERDBNAME
		else:
			self._eventType = 'Alarm'
			self._activeDataBase = self._ALARMDBNAME

		# self.logInfo(f'Setting the current event to **{self._eventType}**')
		self.viewTableValues()


	# Used for setting up a alarm - required
	@IntentHandler('SetUpAlarm')
	def setAlarmIntent(self, session: DialogSession):
		self.addReminder(session)


	# Used for setting up a timer - required
	@IntentHandler('SetUpTimer')
	def setTimerIntent(self, session: DialogSession):
		self.addReminder(session)


	# Used for deleting a item(s) - required
	@IntentHandler('ReminderDelete')
	def deleteRemindersIntent(self, session: DialogSession):
		self.setEventType(session)

		if 'ReminderDeleteAll' in session.slots:
			self.askIfTheDetailsAreCorrect(session)
		else:
			self.getItemFromList(session)



	# Used for when user asks how long left on timer - required
	@IntentHandler('ReminderRemaining')
	def remainingTimeReminderIntent(self, session: DialogSession):
		self.setEventType(session)

		if 'ReminderSlot' in session.slots or 'TimerSlot' in session.slots or 'AlarmSlot' in session.slots:
			self.getItemFromList(session)


	# Used for stopping a event - required
	@IntentHandler('ReminderStop')
	def stopReminderIntent(self, session: DialogSession):

		if 'TimerStop' in session.slots:
			self.setEventType(session)
			self.getItemFromList(session)
		elif 'ReminderStop' in session.slots:
			self.setEventType(session)
			self.getItemFromList(session)
		else:
			self.setEventType(session)
			self.getItemFromList(session)


	@IntentHandler('ReminderTime')
	def addRemiderIntent(self, session: DialogSession):
		pass

	@IntentHandler('ReminderMessage')
	def addReminderIntent(self, session: DialogSession):

		self.processTheSpecifiedTime(session)
