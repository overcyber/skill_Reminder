

import time

from datetime import datetime, timedelta
from core.base.model.AliceSkill import AliceSkill
from core.base.model.Intent import Intent
from core.dialog.model.DialogSession import DialogSession
from core.util.Decorators import IntentHandler

class Reminder(AliceSkill):
	"""
	Author: @Lazza.
	 This skill utilises these main methods for functional operation
		- addReminder initiates the reminder process between user and Alice
		- Then passes onto processTheSpecifiedTime() for processing of the time
		- then onto processAndStoreReminder() for finalising the timer
			Amongst that process there are methods for converting spoken times to epoch and back to human time
			and Various other functions and checks, delete, how long left, etc.
			Also, one main Method which allows switching between the three events (Reminder/Timer/Alarm) is the
		- setEventType() method. This allows the skill to determine what of the 3 events we are dealing with
	"""
	INTERNAL_ID = 'internalId TEXT NOT NULL'
	DB_MESSAGE = 'message TEXT NOT NULL'
	DB_TIMESTAMP = 'timestamp INTEGER NOT NULL'
	DB_SITE_ID = 'SiteID TEXT NOT NULL'
	DB_EVENT_TYPE = 'EventType TEXT NOT NULL'

	_REMINDERDBNAME = 'MyReminders'
	_TIMERDBNAME = 'MyTimer'
	_ALARMDBNAME = 'MyAlarm'
	_DATABASE = {
		_REMINDERDBNAME: [
			INTERNAL_ID,
			DB_MESSAGE,
			DB_TIMESTAMP,
			DB_SITE_ID,
			DB_EVENT_TYPE
		],
		_TIMERDBNAME   : [
			INTERNAL_ID,
			DB_MESSAGE,
			DB_TIMESTAMP,
			DB_SITE_ID,
			DB_EVENT_TYPE
		],
		_ALARMDBNAME   : [
			INTERNAL_ID,
			DB_MESSAGE,
			DB_TIMESTAMP,
			DB_SITE_ID,
			DB_EVENT_TYPE
		]
	}
	_INTENT_PREDEFINED_TIMER = Intent('PreDefinedTimerEvent')
	_INTENT_ADD_REMINDER = Intent('ReminderEvent')
	_INTENT_ADD_DATE = Intent('ReminderTime')
	_INTENT_ANSWER_YES_OR_NO = Intent('AnswerYesOrNo')
	_INTENT_TIME_REMAINING = Intent('ReminderRemaining')
	_INTENT_SELECT_ITEM = Intent('ChooseListItem')
	_INTENT_DELETE_REMINDER = Intent('ReminderDelete')
	_INTENT_USER_RANDOM_ANSWER = Intent('UserRandomAnswer')


	def __init__(self):

		self._spokenDuration = ''
		self._dateTimeStr = ''
		self._dateTimeObject = ''
		self._secondsDuration = 0.0
		self._reminderMessage = ''
		self._dbId = 0
		self._theDeviceId = ""
		self._dbTableValues = list()
		self._selectedMessages = None
		self._dbTimeStampList = list()
		self._dbMessageList = list()
		self._dbRowIdList = list()
		self._dbSiteList = list()
		self._eventType = list()
		self._activeDataBase = 'MyReminders'
		self._dataBaseList = ['MyReminders', 'MyTimer', 'MyAlarm']
		self._TimerEventType = list()
		self._preDefinedEvent = False

		self._INTENTS = [
			(self._INTENT_PREDEFINED_TIMER, self.determinePreDefinedTimer),
			self._INTENT_ANSWER_YES_OR_NO,
			self._INTENT_ADD_DATE,
			self._INTENT_SELECT_ITEM,
			self._INTENT_USER_RANDOM_ANSWER,
			(self._INTENT_ADD_REMINDER, self.addReminder)
		]

		# init Dialog mapping to prevent dialog clashing with other skills
		self._INTENT_ANSWER_YES_OR_NO.dialogMapping = {
			'ConfirmIfDeletingAllMessages': self.actionFromYesNoAnswer,
			# 'ConfirmIfMessageAndTimeCorrect': self.processTheSpecifiedTime

		}
		self._INTENT_PREDEFINED_TIMER.dialogMapping = {
			'DoPredefinedTimerEvent': self.determinePreDefinedTimer,

		}

		self._INTENT_ADD_REMINDER.dialogMapping = {
			'AddMessageToReminder': self.processTheSpecifiedTime
		}

		self._INTENT_USER_RANDOM_ANSWER.dialogMapping = {
			'AddMessageToReminder': self.processTheSpecifiedTime
		}

		self._INTENT_DELETE_REMINDER.dialogMapping = {
			'DeleteSomeReminder': self.deleteRequestedReminder
		}

		self._INTENT_SELECT_ITEM.dialogMapping = {
			'SelectedItemFromList': self.extractRequestedItemFromList,
			'askWhatItemFromList' : self.extractRequestedItemFromList
		}

		self._INTENT_ADD_DATE.dialogMapping = {
			'AddedTheDateOrDuration': self.addReminder,

		}
		super().__init__(self._INTENTS, databaseSchema=self._DATABASE)


	# Cleanup the Db on boot up
	def onStart(self):
		super().onStart()
		self.logInfo(f'Doing database maintenance')
		self.cleanupDeadTimers()
		self.onFiveMinute()

	def runShortTimer(self, event: str):
		self.reminderSound(event)
		self.ThreadManager.doLater(
			interval=0.5,
			func=self.say(
				text='Your short timer has finished'
			),
		)

	def onBooted(self) -> bool:
		self._theDeviceId = self.DeviceManager.getMainDevice().uid
		super().onBooted()
		return True

	def findTheSeconds(self, session):

		secs : int = 0
		if 'Duration' in session.slots:
			self._secondsDuration = self.Commons.getDuration(session)
			secs = self._secondsDuration

		if f'{self._eventType}DateAndTime' in session.slotsAsObjects:
			self._spokenDuration = session.slotValue(f'{self._eventType}DateAndTime').split()  # returns format [2020-04-08, 10:25:00, +10]
			del self._spokenDuration[-1]  # Removes the timezone off the end
			self._dateTimeStr = ' '.join(self._spokenDuration)  # converts the list to a string
			self._dateTimeObject  = datetime.strptime(self._dateTimeStr, '%Y-%m-%d %H:%M:%S')
			self._secondsDuration  = self._dateTimeObject - datetime.today()  # find the difference between requested time and now

			self.setEventType(session)
			secs = round(self._secondsDuration.total_seconds())

		food = False
		if 'Food' in session.slots:
			food = True

		return food, secs

	def addReminder(self, session: DialogSession):
		"""
		Ask user for missing details or triggers a short timer if that was requested
		"""
		food, secs = self.findTheSeconds(session)

		# if user set a short timer (no topic) do this
		if 'ShortTimer' in session.slots and 'Duration' in session.slots:
			self._reminderMessage = 'for the timer with no topic'

			self.ThreadManager.doLater(
				interval=self._secondsDuration,
				func=self.runShortTimer,
				args=[self._eventType]
			)
			self.endDialog(
				sessionId=session.sessionId,
				text=f'ok, done'
			)
			return

		# If there's an event date or duration specified then ask for a message
		if f'{self._eventType}DateAndTime' in session.slots or 'Duration' in session.slots:

			self.continueDialog(
				sessionId=session.sessionId,
				text=self.randomTalk(text='respondReminderMessage', replace=[self._eventType]),
				intentFilter=[self._INTENT_USER_RANDOM_ANSWER],
				customData={
					"seconds" : secs,
					"food" : food
				},
				currentDialogState='AddMessageToReminder'
			)
		# If there's no time set then ask for one
		else:
			if f'{self._eventType}DateAndTime' not in session.slots or 'Duration' not in session.slots:
				self.continueDialog(
					sessionId=session.sessionId,
					text=self.randomTalk(text='respondSetDuration', replace=[self._eventType]),
					intentFilter=[self._INTENT_ADD_DATE],
					currentDialogState='AddedTheDateOrDuration',
					slot='ReminderDateAndTime' or 'Duration'
				)

	def determinePreDefinedTimer(self, session: DialogSession):
		"""
		Work out what pre-determined timer event it is and set the message and time accordingly
		:param session: the dialog Session
		:return:
		"""
		# set some vars so, we can merge the event with existing timer code
		self._theDeviceId = session.deviceUid
		self._eventType = 'Timer'
		self._activeDataBase = self._TIMERDBNAME
		self._preDefinedEvent = True

		# work out what pre-determined timer the user is requesting
		if session.slotValue('PreDefinedTimer') == 'wash hands':
			session.payload['input'] = self.randomTalk(text='washingHands')
			self.processTheSpecifiedTime(session, preDefinedTime=20)

		if session.slotValue('PreDefinedTimer') == 'brush teeth':
			session.payload['input'] = self.randomTalk(text='brushingTeeth')
			self.processTheSpecifiedTime(session, preDefinedTime=120)

		if session.slotValue('PreDefinedTimer') == 'cup of tea':
			session.payload['input'] = self.randomTalk(text='teaReady', replace=['cup'])
			self.processTheSpecifiedTime(session, preDefinedTime=180)

		if session.slotValue('PreDefinedTimer') == 'pot of tea':
			session.payload['input'] = self.randomTalk(text='teaReady', replace=['pot'])
			self.processTheSpecifiedTime(session, preDefinedTime=420)


	def processTheSpecifiedTime(self, session: DialogSession, preDefinedTime: int = None):
		"""
		Process the requested Time/Date/Duration, so we can later use that in the reminder
		:param session: The dialog Session
		:param preDefinedTime: If it's a preDefinedTimer event then this will be the seconds of the timer to use
		:return:
		"""

		if preDefinedTime:
			self._reminderMessage = session.payload['input']  # set the reminder message
			self.processAndStoreReminder(session=session, secs=preDefinedTime)
			return

		self._reminderMessage = session.payload['input']  # set the reminder message

		if session.customData['food']:
			self.setFoodTimer(session, session.customData['seconds'])

		else:
			self.processAndStoreReminder(session, session.customData['seconds'])



	def processAndStoreReminder(self, session: DialogSession, secs: int):
		"""
		This does the actual setting of the event and the storing to the database
		:param session: The dialog Session
		:param secs: The seconds between "now" and when the event is to trigger
		:return:
		"""
		self.logDebug(f'The requested time converted to seconds is {secs}')

		# count of the amount of rows in the Database
		myTablecount = self.tableRowCount()

		# Convert to Epoch timestamp in Seconds for storing in Db

		timeStampForDb = self.createEpochTimeStamp(secs)

		# VocalSeconds is used to give Alice's reply a human friendly response
		vocalSeconds = str(timedelta(seconds=secs))

		hour, minute, second = vocalSeconds.split(':')
		vocalTime = ''

		try:
			hours = int(hour)
			minutes = int(minute)
			seconds = int(second)
		except ValueError:
			self.logWarning(self.randomTalk(text="systemMessage3"))
			hours = 0
			minutes = 0
			seconds = 60

		if seconds > 0:
			vocalTime = f'{seconds} seconds'
		if minutes > 0:
			if minutes > 1:
				if seconds > 0:
					vocalTime = f'{minutes} minutes and {vocalTime}'
				else:
					vocalTime = f'{minutes} minutes'
			else:
				if seconds > 0:
					vocalTime = f'{minutes} minute and {vocalTime}'
				else:
					vocalTime = f'{minutes} minute'
		if hours > 0:
			if hours > 1:
				vocalTime = f'{hours} hours, {vocalTime}'
			else:
				vocalTime = f'{hours} hour and {vocalTime}'


		# Set event type for later recall from db when dofiveMinute is called after a reboot
		self._TimerEventType = self._eventType

		if secs < 299:
			self.ThreadManager.doLater(
				interval=secs,
				func=self.runReminder,
				args=[self._eventType, self._reminderMessage]
			)

		# write Timer info to the database or not depending on length of time (saves double up reminder from onFive trigger
		try:
			if secs >= 299:
				self.databaseInsert(
					tableName=self._activeDataBase,
					values={'internalID': myTablecount + 1, 'message': self._reminderMessage, 'timestamp': timeStampForDb, 'SiteID': self._theDeviceId, 'EventType': self._eventType}
				)
		except Exception as e:
			self.logError(f'Failed to enable timer due to **Database** error: {e}')
			self.endDialog(
				sessionId=session.sessionId,
				text=self.randomTalk('databaseError')
			)
			return

		# Alice Confirming that the Reminder has been set ..........................................................
		self.endDialog(
			sessionId=session.sessionId,
			text=self.randomTalk('respondConfirmed', replace=[self._eventType, self._reminderMessage, vocalTime])
		)


	# Respond with The Reminder once time is finished,
	def runReminder(self, event: str, savedMessage: str):
		self.reminderSound(event)
		self.ThreadManager.doLater(interval=5, func=self.say, kwargs={'text': self.randomTalk(text='respondReminder', replace=[event, savedMessage]), 'deviceUid': self._theDeviceId})


	def foodReminder(self):
		self.say(self.randomTalk(text='respondFoodTimer'), deviceUid=self._theDeviceId)


	# required
	@staticmethod
	def createEpochTimeStamp(seconds: int) -> int:
		timeStampForDatabase = datetime.now() + timedelta(seconds=seconds)
		dateTime = str(timeStampForDatabase)
		pattern = '%Y-%m-%d %H:%M:%S.%f'
		epoch = int(time.mktime(time.strptime(dateTime, pattern)))
		return epoch


	# Sets a mid-timer, timer to alert to go check the food
	def setFoodTimer(self, session: DialogSession, secs):
		checkTheFoodTimer = secs / 2
		self.ThreadManager.doLater(
			interval=checkTheFoodTimer,
			func=self.foodReminder
		)
		self.processAndStoreReminder(session, secs)


	def askIfTheDetailsAreCorrect(self, session: DialogSession):

		if 'ReminderDeleteAll' in session.slots:
			self.continueDialog(
				sessionId=session.sessionId,
				text=self.randomTalk('respondAskConfirmation', replace=[self._eventType]),
				intentFilter=[self._INTENT_ANSWER_YES_OR_NO],
				currentDialogState='ConfirmIfDeletingAllMessages',
				probabilityThreshold=0.1
			)


	# do something in responce to a yes or no reply
	def actionFromYesNoAnswer(self, session: DialogSession):

		if 'ConfirmIfDeletingAllMessages' in session.currentState:

			if self.Commons.isYes(session):
				self.deleteRequestedReminder(session)
			else:
				self.endDialog(
					sessionId=session.sessionId,
					text=self.randomTalk('respondToANoReply', replace=[self._eventType]),
				)


	# This returns the amount of rows in the database table
	# TODO: this should not be used for calculating the index, but returned by the db on insert!
	def tableRowCount(self) -> int:
		return self.databaseFetch(tableName=self._activeDataBase, query='SELECT COUNT () AS c FROM :__table__')[0]['c']


	# This updates the internalID value to match table rowid
	def updateInternalIdNumberOfDb(self):
		i = 0
		while i <= len(self._dataBaseList) - 1:
			if i == 0:
				self._eventType = 'Reminder'
				self._activeDataBase = self._REMINDERDBNAME
			elif i == 1:
				self._eventType = 'Timer'
				self._activeDataBase = self._TIMERDBNAME
			else:
				self._eventType = 'Alarm'
				self._activeDataBase = self._ALARMDBNAME
			self.viewTableValues()

			try:
				# noinspection SqlResolve
				self.DatabaseManager.update(
					tableName=self._activeDataBase,
					callerName=self.name,
					query='UPDATE :__table__ SET internalId = rowid'
				)
			except:
				self.ThreadManager.doLater(
					interval=300,
					func=self.updateInternalIdNumberOfDb
				)
			i += 1



	def viewTableValues(self):
		"""
		Retrieve all database values and put into vars to reduce database reads later on
		"""
		# self.updateInternalIdNumberOfDb()  # resets internalId column to rowid value

		# Todo What??
		# Answer = try and reduce db reads
		self._dbTableValues = list()
		for row in self.databaseFetch(tableName=self._activeDataBase, query='SELECT * FROM :__table__ '):
			if row:
				self._dbTableValues.append(row)

		self._dbSiteList = [x['SiteID'] for x in self._dbTableValues]  # get list of SiteId for use on an Alice restart
		self._dbTimeStampList = [x['timestamp'] for x in self._dbTableValues]  # get list of TimeStamps
		self._dbMessageList = [x['message'] for x in self._dbTableValues]  # get the list of messages
		self._dbRowIdList = [x['internalId'] for x in self._dbTableValues]  # get The list of row ID's
		self._TimerEventType = [x['EventType'] for x in self._dbTableValues]  # get event type from db

		self.cleanupDeadTimers()


	# Returns the remaining time left on a choosen timer
	def getTimeRemaining(self, session: DialogSession):
		convertedTime = self.convertEpochMinusNowToHumanReadableTime()

		self.endDialog(
			sessionId=session.sessionId,
			text=self.randomTalk('respondTimeRemaining', replace=[convertedTime, self._eventType]),
			deviceUid=session.deviceUid
		)


	# This starts the process of asking user what item to look up in the list
	def getItemFromList(self, session: DialogSession):
		completeMessageString = ''

		i = 0
		# Reads a list of items and adds it to one string
		for x in self._dbMessageList:
			i += 1
			commonString = f'The {self._eventType} number {i} <break time=\"250ms\"/>.'
			completeMessageString = f'{completeMessageString} {commonString} {x} <break time=\"250ms\"/>,'

		if len(self._dbMessageList) == 0:
			self.endDialog(
				sessionId=session.sessionId,
				text=self.randomTalk('respondNoActive', replace=[self._eventType])
			)

		elif len(self._dbMessageList) == 1:
			self._selectedMessages = self._dbMessageList[0]

			if 'ReminderDeleteAll' in session.slotsAsObjects or 'ReminderDelete' in session.slotsAsObjects:
				self.deleteRequestedReminder(session)

			elif f'{self._eventType}RemainingTime' in session.slotsAsObjects:
				self.getTimeRemaining(session)

			elif f'{self._eventType}Stop' in session.slotsAsObjects:
				self.userAskedToStopReminder(session)

			else:
				return
		else:
			self.askForWhichItems(session, self._dbMessageList, completeMessageString)


	# This is used for asking the user to select the item from a list and return it to extractRequestedItemFromList()
	def askForWhichItems(self, session: DialogSession, dbMessageList: list, completeMessageString: str):
		dbMessageList.insert(0, self._eventType)

		self.continueDialog(
			sessionId=session.sessionId,
			text=self.randomTalk('respondListOfItems', replace=[completeMessageString]),  # replace=[message for message in self._dbMessageList]),
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
				itemChosen = int(itemChosen) - 1  # turn float into an int then subtract 1 for indexing the list
				self._selectedMessages = self._dbMessageList[itemChosen]  # extract the actual requested message

				if 'ReminderDelete' in session.slotsAsObjects:
					self.deleteRequestedReminder(session)

				elif f'{self._eventType}RemainingTime' in session.slotsAsObjects:
					self.getTimeRemaining(session)

				elif f'{self._eventType}Stop' in session.slotsAsObjects:
					self.userAskedToStopReminder(session)

			else:
				self.continueDialog(
					sessionId=session.sessionId,
					text='respondNoNumber',
					intentFilter=[self._INTENT_SELECT_ITEM],
					currentDialogState='askWhatItemFromList'
				)
		else:
			self.logWarning(f'The expected Intent was not received')


	def cleanupDeadTimers(self):

		i = 0

		for x in self._dbTimeStampList:  # x = a individual timestamp from _dbTimeStampList
			epochTimeNow = datetime.now().timestamp()  # Returns the epoch time for right now

			if x < epochTimeNow:

				# noinspection SqlResolve
				self.DatabaseManager.delete(
					tableName=self._activeDataBase,
					query='DELETE FROM :__table__ WHERE timestamp <= :tmpTimestamp',
					values={'tmpTimestamp': epochTimeNow},
					callerName=self.name
				)
				i += 1

		if i > 0:
			self.viewTableValues()
			self.logDebug(f'Just deleted {i} redundant event/s from {self._activeDataBase}')


	# This stops a current timer on request
	def userAskedToStopReminder(self, session: DialogSession):
		self.setEventType(session)

		# noinspection SqlResolve
		self.DatabaseManager.delete(
			tableName=self._activeDataBase,
			query='DELETE FROM :__table__ WHERE message = :tmpMessage',
			values={'tmpMessage': self._selectedMessages},
			callerName=self.name)

		self.endDialog(
			sessionId=session.sessionId,
			text=self.randomTalk('respondDelete', replace=[self._eventType]),
			deviceUid=session.deviceUid
		)
		self.cleanupDeadTimers()


	# Used to Convert the Database Timestamp into seconds
	def convertEpochMinusNowToSeconds(self, epochSeconds: int = None) -> float:
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

			timestampActual = self._dbTableValues[indexPos]['timestamp']
			differenceInSeconds = (timestampActual - epochTimeNow)

			return differenceInSeconds


	# Converts Epoch time from DB to a Human readable output
	def convertEpochMinusNowToHumanReadableTime(self) -> str:
		convertedToSeconds = self.convertEpochMinusNowToSeconds()

		return str(timedelta(seconds=round(convertedToSeconds)))


	# This deletes an Item from DB the cleans up the row id's
	def deleteRequestedReminder(self, session: DialogSession):
		self.setEventType(session)

		if 'ReminderDeleteAll' not in session.slots:
			# noinspection SqlResolve
			self.DatabaseManager.delete(
				tableName=self._activeDataBase,
				query='DELETE FROM :__table__ WHERE message = :tmpMessage',
				values={'tmpMessage': self._selectedMessages},
				callerName=self.name)

			self.endDialog(
				sessionId=session.sessionId,
				text=self.randomTalk('respondDelete', replace=[self._eventType]),
				deviceUid=session.deviceUid,
			)

			self.logInfo(f'Successfully deleted the requested {self._eventType} from the database')
			return
		else:
			self.endDialog(
				sessionId=session.sessionId,
				text=self.randomTalk('respondDeleteAll', replace=[self._eventType]),
				deviceUid=session.deviceUid,
			)
			# noinspection SqlWithoutWhere
			self.DatabaseManager.delete(
				tableName=self._activeDataBase,
				query='DELETE FROM :__table__ ',
				callerName=self.name
			)
		self.cleanupDeadTimers()


	# This does a 5-minute check of the stored timers and if a timer is within 299 seconds of activating
	# then we initiate the actual timer thread
	def onFiveMinute(self):
		self.viewTableValues()

		i = 0

		while i <= len(self._dataBaseList) - 1:
			self._activeDataBase = self._dataBaseList[i]
			if 'MyReminder' in self._activeDataBase:
				self._eventType = 'Reminder'
			elif 'MyTimer' in self._activeDataBase:
				self._eventType = 'Timer'
			else:
				self._eventType = 'Alarm'

			self.viewTableValues()
			self.logDebug(f'Checking for active timers in {self._activeDataBase} database')

			for x in self._dbTableValues:
				timerMessage = x['message']
				self._TimerEventType = x['EventType']
				theSeconds = x['timestamp']
				convertedTime = self.convertEpochMinusNowToSeconds(theSeconds)
				float(convertedTime)
				vocalSeconds = str(timedelta(seconds=round(convertedTime)))
				self.logDebug(f'You have a {self._TimerEventType} with {vocalSeconds} left on it')
				cleanUpSeconds = convertedTime + 20.0

				if convertedTime < 299.0:
					self.ThreadManager.doLater(
						interval=convertedTime,
						func=self.runReminder,
						args=[self._TimerEventType, timerMessage]
					)
					self.ThreadManager.doLater(
						interval=cleanUpSeconds,
						func=self.viewTableValues
					)
			i += 1


	def reminderSound(self, event: str):

		path = event
		if 'Reminder' in event:
			soundFile = 'Reminder.wav'
		elif 'Timer' in event:
			soundFile = 'Timer.wav'
		else:
			soundFile = 'Alarm.wav'

		self.playSound(
			soundFilename=soundFile,
			location=self.getResource(f'Sounds/{path}'),
			sessionId='ReminderTriggered',
			deviceUid=self._theDeviceId
		)


	# Critical method for allowing reminder/timer/alarm to all play nicely together
	def setEventType(self, session: DialogSession):
		self._theDeviceId = session.deviceUid

		if 'ReminderEvent' in session.slots or 'ReminderSlot' in session.slots or 'ReminderStop' in session.slots:
			self._eventType = 'Reminder'
			self._activeDataBase = self._REMINDERDBNAME
		elif 'TimerEvent' in session.slots or 'TimerSlot' in session.slots or 'TimerStop' in session.slots:
			self._eventType = 'Timer'
			self._activeDataBase = self._TIMERDBNAME
		else:
			self._eventType = 'Alarm'
			self._activeDataBase = self._ALARMDBNAME

		self.viewTableValues()


	# Used for setting up an alarm - required
	@IntentHandler('SetUpAlarm')
	def setAlarmIntent(self, session: DialogSession):
		self.setEventType(session)
		self.addReminder(session)


	# Used for setting up a timer - required
	@IntentHandler('SetUpTimer')
	def setTimerIntent(self, session: DialogSession):
		self.setEventType(session)
		self.addReminder(session)


	# Used for deleting an item(s) - required
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


	# Used for stopping an event - required
	@IntentHandler('ReminderStop')
	def stopReminderIntent(self, session: DialogSession):
		self.setEventType(session)
		self.getItemFromList(session)


	@IntentHandler('ReminderMessage')
	def addReminderIntent(self, session: DialogSession):
		self.processTheSpecifiedTime(session)
