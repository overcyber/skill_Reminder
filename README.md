# Reminder

[![Continous Integration](https://gitlab.com/project-alice-assistant/skills/skill_Reminder/badges/master/pipeline.svg)](https://gitlab.com/project-alice-assistant/skills/skill_Reminder/pipelines/latest) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=project-alice-assistant_skill_Reminder&metric=alert_status)](https://sonarcloud.io/dashboard?id=project-alice-assistant_skill_Reminder)

Set local reminders such as "Set a reminder in 10 minutes to ring bob"

- Author: Lazza
- Maintainers: Psycho, Philipp
- Alice minimum Version: 1.0.0-b1
- Languages:
    en
	de

**Using this Reminder:**

You can set a reminder / timer or alarm by saying the following examples to Alice

- Set a reminder for 10 minutes
- set a timer for 10 minutes
- set a alarm for 10 minutes

In the following utternaces you can do as above to change between reminder or timer or alarm 
( just say reminder instead of timer or alarm )

 - "Set a alarm for 1 hour",
 - "Set a alarm for 1 minute",
 - "Can you create a timer for 3 hours please",
 - "Set a reminder in 10 minutes",
 - "create a reminder for 20 miuntes please",
 - "Set a 15 minute timer please",
 - "Set a reminder for tuesday at 8 am",
 - "Set a alarm for 8 am tomorrow",
 - "Add a 20 minute timer",
 - "create a reminder for 2 pm",
 - "Add a timer for 4pm"
 
 Alice will then ask you to set a message for the timer/reminder/alarm
 
 The reminder will then get stored in the database so if you reboot Alice she will
 restart the reminder on startup. Redundant timers will get deleted automagically
 
 You can also ask her things like :
 
 "How long is left on my timer"
  Alice will then tell you the remaining time if you only have one timer set
  Otherwise if you have multiple timers she will then respond with a list of the active timers
  that you have.
  
  To select the correct timer respond with the number of the timer she has just mentioned
  IE : " number 1"
    or reminder number 2
    
  same applies if you ask alice to "delete a reminder"
  If you ask her to delete all reminders she will ummmm....delete all reminders, after prompting you to confirm :) 
 
 **Additional events** :
 - Asking Alice to set a "Food Timer" will let alice know your cooking and therefore she will remind 
    you half way through the timer to check your food.
 - Alice can now set a "Timer" (only) without a message by saying things like
    * set a quick timer for 3 minutes
    * create a short timer for 2 minutes
    * keywords to trigger this are : "quick", "short" "breif", "simple", "lazy"
    and she will now set a timer event without the need for a topic
    
    NOTE: the limitation on this quick timer function are.
    * if you reboot you'll loose the timer 
    * you wont be able to stop the timer as it has no topic
    * you won't be able to ask how longs left on the timer as it has no topic
    * This only works for timer event, not reminder or alarm events
     
 **Sound folder**
 
 There is a sound folder with a seperate folder for each event.
 To replace the sound file with one of your choice just make sure the new sound file is named
    the same. IE: Reminder.wav unless you want to edit the code to suit
 
 **Potential future enhancments**
   - Add a widget to :
                     * enable/disable sounds
                     * choose sound files to use
                     * Set "food timer" mid point reminder time 
    
NOTES. *This will not work effectively using the text input widget due to several settings requiring continued dialog*
