import logging
import re
import os
import mysql.connector
from dotenv import load_dotenv
from mysql.connector import Error
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, CallbackQueryHandler, CallbackContext, filters
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot

# Should be saved at 110124 1035h

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Variables
load_dotenv()
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))
TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(TOKEN)
ASSOC_CHAT_ID = os.getenv('ASSOC_CHAT_ID')

# Define conversation states
(FIRST_NAME, LAST_NAME, DATE_OF_BIRTH, PHOTO_UPLOAD, NRIC_NUMBER, MOE_IRS, MOBILE, POSTAL, LOCKREG) = range(9)
(SCHOOL, PROG_DATE, START_TIME, HOURS, STUDENT_LEVEL, TRAINERS_NEEDED, PROGRAMME_NAME, CONFIRM) = range(8)
(SELECT_DATE, LIST_END) = range(2)
(APPLY_JOB, CONFIRM_APPLY, ANOTHER_JOB) = range(3)
(ACCEPT_OR_REJECT, PROCESS_ACCEPT, PROCESS_REJECT) = range(3)
(USER_OPTIONS, WITHDRAW_CONFIRMATION, ENTER_PROGRAMME_ID, CONFIRM_WITHDRAWAL) = range(4)
(COMPLETE_OR_CANCEL, ANY_REMOVALS, CONFIRM_ALL_PROG_DEETS) = range(3)


# MAIN DB CONNECTOR
def create_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_DATABASE'),
            user=os.getenv('DB_USERNAME'),
            password=os.getenv('DB_PASSWORD')
        )
        if connection.is_connected():
            db_info = connection.get_server_info()
            print("Connected to MySQL Server version ", db_info)
            return connection
    except Error as e:
        print("Error while connecting to MySQL", e)
        return None


# CALLBACK QUERY
async def handle_callback_query(update, context):
    query = update.callback_query
    await query.answer()
    # Retrieve the callback data
    data = query.data

    if data == 'home':
        # Main page
        keyboard = [
            [InlineKeyboardButton("List all programmes", callback_data='list')],
            [InlineKeyboardButton("Sign up for a programme", callback_data='signup')],
            [InlineKeyboardButton("Profile", callback_data='profile')],
            [InlineKeyboardButton("Manage Sign Ups", callback_data='myprog')],
            [InlineKeyboardButton("About Haley", callback_data='about')],
        ]
        reply_markup1 = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="Hello you!", reply_markup=reply_markup1)
    elif data == 'list':
        # For listing of all programmes
        await list_jobs(update, context)
    elif data == 'signup':
        # To sign up for programmes
        await apply_job_handler(update, context)
    elif data == 'register':
        # Call the register function or redirect the user to the registration process
        await register(update, context)
    elif data == 'add_prog':
        # To add a new programme
        await start_addprog(update, context)
    elif data == 'view_prog_id':
        # To add a new programme
        await view_sesh_id(update, context)
    elif data == 'view_app':
        # To view all applications for a programme
        await view_applications(update, context)
    elif data == 'accept_app':
        # To accept trainers into a programme
        await app_accept_button(update, context)
    elif data == 'reject_app':
        # To reject trainers for a programme
        await app_reject_button(update, context)
    elif data == 'profile':
        # To view user profile, including training hours
        await view_personal_profile(update, context)
    elif data == 'myprog':
        # To see list of programmes pending or confirmed
        await view_user_apps(update, context)
    elif data == 'complete_programme':
        # To complete the programme
        await complete_prog(update, context)
    elif data == 'about':
        # General about text
        await about_bot(update, context)


# COMMANDS
async def start(update, context):
    user_id = update.message.from_user.id

    try:
        member = await context.bot.get_chat_member(ASSOC_CHAT_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            await update.message.reply_text("Hello! I am Haley, thanks for joining us!")
            keyboard = [
                [InlineKeyboardButton("Register", callback_data='register')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                'Please register for an account to continue. You will need your MOE IRS email handy so get that ready!',
                reply_markup=reply_markup)
        else:
            await update.message.reply_text("Sorry but I can only help Halogen Associates! Join us first? Head to https://halogen.sg/halogenplus-volunteer/ to sign up!")
    except Error:
        await update.message.reply_text("Sorry there was an error! Are you already a Halogen Associate? If so try again, if not you can head to https://halogen.sg/halogenplus-volunteer/ to sign up!")


async def manager_home(update, context):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    # Verify if the user is a manager
    if not is_user_manager(user_id):
        await update.message.reply_text("Er no...maybe ask Tim to add you?")
        return

    keyboard = [
        [InlineKeyboardButton("Add a new programme", callback_data='add_prog')],
        [InlineKeyboardButton("View applications", callback_data='view_app')],
        [InlineKeyboardButton("Accept applicants", callback_data='accept_app')],
        [InlineKeyboardButton("Reject applicants", callback_data='reject_app')],
        [InlineKeyboardButton("View Programme ID", callback_data='view_prog_id')],
        [InlineKeyboardButton("Mark Programme as Complete", callback_data='complete_programme')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text="Cool! Here are your admin options.", reply_markup=reply_markup)


async def set_user_role(update, context):
    # Check if the command is used in a private chat
    if update.message.chat.type != 'private':
        await update.message.reply_text("This command can only be used in private messages.")
        return

    # Check if the user who sent this command is the admin
    if update.message.from_user.id != ADMIN_USER_ID:
        await update.message.reply_text("You don't have permission to use this command.")
        return

    # Extract user ID and role from the admin user input
    try:
        user_id, role = context.args
    except ValueError:
        await update.message.reply_text("Usage: /setrole <user_id> <role>")
        return

    # Update the user's role in the database
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            update_query = "UPDATE users SET account_type = %s WHERE telegram_id = %s"
            cursor.execute(update_query, (role, user_id))
            connection.commit()
            await update.message.reply_text(f"Updated user {user_id} to {role}.")
        except Error as e:
            await update.message.reply_text("Error while updating the role in MySQL.")
            print("Error while updating MySQL", e)
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        await update.message.reply_text("Failed to connect to the database.")


async def view_personal_profile(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = query.from_user.id

    # Check if the command is used in a private chat
    if query.message.chat.type != 'private':
        await context.bot.send_message(chat_id=chat_id, text="This command can only be used in private messages.")
        return

    await query.edit_message_reply_markup(reply_markup=None)

    # Retrieve personal details
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            query = """
                        SELECT first_name, last_name, date_of_birth, nric_number, 
                               moe_irs, mobile, postal, training_hours 
                        FROM users
                    """
            cursor.execute(query)
            users = cursor.fetchall()

            if not users:
                await context.bot.send_message(chat_id=chat_id, text="No details found. Are you registered?")
                return

            profiles = "Your registered details:\n\n"
            for user in users:
                profiles += (f"• First Name: {user[0]}\n• Last Name: {user[1]}\n"
                             f"• Date of Birth: {user[2]}\n• NRIC: {user[3]}\n"
                             f"• MOE IRS Expiry: {user[4]}\n• Mobile: {user[5]}\n"
                             f"• Postal Code: {user[6]}\n• Training Hours: {user[7]}\n\n")
            await context.bot.send_message(chat_id=chat_id, text=profiles)
            keyboard = [
                [InlineKeyboardButton("Go to Main Page", callback_data='home')]
            ]
            reply_markup1 = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=chat_id, text="If you need to edit any of these details, please approach the Halogen team.", reply_markup=reply_markup1)
            return

        except Error as e:
            return f"Error fetching user profiles: {e}"
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        await context.bot.send_message(chat_id=chat_id, text="Failed to connect")


async def about_bot(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = query.from_user.id

    # Check if the command is used in a private chat
    if query.message.chat.type != 'private':
        await context.bot.send_message(chat_id=chat_id, text="This command can only be used in private messages.")
        return

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=chat_id, text="Haley is a bot programmed by Halogen to allow Associates to view and manage programme signups. Ask your friends to join us in this impactful work! https://halogen.sg/halogenplus-volunteer/")


# CONVERSATION 1 - REGISTER FOR ACCOUNT - FIRST_NAME TO LOCKREG
async def register(update, context):
    query = update.callback_query
    await query.answer()

    # Check if the command is used in a private chat
    if query.message.chat.type != 'private':
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="This command can only be used in private messages.")
        return ConversationHandler.END

    tele_id = update.callback_query.from_user.id

    # Verify if the user is registered
    if is_user_registered(tele_id):
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="You are already registered.")
        return ConversationHandler.END

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Please enter your first name.")
    return FIRST_NAME


def is_user_registered(tele_id):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE telegram_id = %s", (tele_id,))
            (count,) = cursor.fetchone()
            return count > 0
        except Error as e:
            print("Error while checking user registration", e)
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return False


async def first_name_handler(update, context):
    context.user_data['first_name'] = update.message.text
    await update.message.reply_text('Great! Now please enter your last name.')
    return LAST_NAME


async def last_name_handler(update, context):
    context.user_data['last_name'] = update.message.text
    await update.message.reply_text('Got it! Now, please enter your date of birth (DDMMYY).')
    return DATE_OF_BIRTH


async def date_of_birth_handler(update, context):
    dob_input = update.message.text
    # Parse date from DDMMYY format
    try:
        dob = datetime.strptime(dob_input, '%d%m%y')
        formatted_dob = dob.strftime('%Y-%m-%d')  # Convert to YYYY-MM-DD format
        context.user_data['date_of_birth'] = formatted_dob
        await update.message.reply_text(
            'Thanks! Please send me a photo of yourself - and just yourself! No group pictures k!')
        return PHOTO_UPLOAD
    except ValueError:
        # Inform the user if the format is incorrect and ask them to re-enter the date
        await update.message.reply_text("Invalid date format. Please enter your date of birth in DDMMYY format.")
        return DATE_OF_BIRTH


async def photo_handler(update, context):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_binary = await file.download_as_bytearray()
    context.user_data['photo'] = photo_binary
    await update.message.reply_text("Looking good! Now we will need your NRIC number in full to verify against the MOE IRS records. Don't worry, I'll keep it safe. ;)")
    return NRIC_NUMBER


async def nric_number_handler(update, context):
    user_nric_number = update.message.text

    # Define the regex pattern for NRIC
    pattern1 = r'^[FGSTfgst][0-9]{7}[A-Za-z]$'

    # Check if the entered NRIC matches the pattern
    if re.match(pattern1, user_nric_number):
        context.user_data['nric_number'] = user_nric_number
        await update.message.reply_text('What is the expiry date (DDMMYY) of your MOE IRS confirmation? You can search for sender@rems.moe.edu.sg to find the email. If you are not registered with MOE IRS, key in 010101')
        return MOE_IRS
    else:
        await update.message.reply_text('Invalid NRIC format. Please enter a valid NRIC number.')
        return NRIC_NUMBER


async def moe_irs_handler(update, context):
    irs_input = update.message.text
    # Parse date from DDMMYY format
    try:
        irs = datetime.strptime(irs_input, '%d%m%y')
        formatted_irs = irs.strftime('%Y-%m-%d')  # Convert to YYYY-MM-DD format
        context.user_data['moe_irs'] = formatted_irs
        await update.message.reply_text(
            'Please enter your mobile number')
        return MOBILE
    except ValueError:
        # Inform the user if the format is incorrect and ask them to re-enter the date
        await update.message.reply_text("Invalid date format. Please enter your date of expiry in DDMMYY format.")
        return MOE_IRS


async def mobile_handler(update, context):
    user_phone_number = update.message.text

    # Define the regex pattern for mobile
    pattern2 = r'^[8-9]{1}[0-9]{7}$'

    # Check if the entered mobile matches the pattern
    if re.match(pattern2, user_phone_number):
        context.user_data['mobile'] = user_phone_number
        await update.message.reply_text('Please enter your residential postal code.')
        return POSTAL
    else:
        await update.message.reply_text('Invalid format. Please enter a valid mobile number.')
        return MOBILE


async def postal_handler(update, context):
    context.user_data['postal'] = update.message.text
    context.user_data['telegram_id'] = update.message.from_user.id
    context.user_data['telegram_username'] = update.message.from_user.username  # Note: Username might be None

    user_postal_code = update.message.text

    # Define the regex pattern for mobile
    pattern3 = r'^[0-9]{6}$'

    # Check if the entered mobile matches the pattern
    if re.match(pattern3, user_postal_code):
        context.user_data['postal'] = user_postal_code
    else:
        await update.message.reply_text('Invalid format. Please enter a valid postal code.')
        return POSTAL

    # Converting dob readable formats
    dob_date_str = context.user_data['date_of_birth']
    dob_date_a = datetime.strptime(dob_date_str, '%Y-%m-%d')
    formatted_dob_date = dob_date_a.strftime('%d %b %y')  # '04 Jan 23'

    # Assemble a summary of the collected data
    biodata_summary = (
        f"First Name: {context.user_data['first_name']}\n"
        f"Last Name: {context.user_data['last_name']}\n"
        f"DOB: {formatted_dob_date}\n"
        f"NRIC: {context.user_data['nric_number']}\n"
        f"MOE IRS Expiry: {context.user_data['moe_irs']}\n"
        f"Mobile Number: {context.user_data['mobile']}\n"
        f"Postal Code: {context.user_data['postal']}\n"
    )

    keyboard = [
        [InlineKeyboardButton("Confirm", callback_data='confirm_reg')],
        [InlineKeyboardButton("Cancel", callback_data='cancel_reg')],
    ]
    reply_markup1 = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please review your personal details:\n" + biodata_summary, reply_markup=reply_markup1)

    return LOCKREG  # Which either goes to handle_reg_confirm or handle_reg_cancel


async def handle_reg_confirm(update, context):
    query = update.callback_query
    await query.answer()

    store_new_user(context.user_data)

    keyboard = [
        [InlineKeyboardButton("Take me there!", callback_data='home')]
    ]
    reply_markup1 = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Registration complete! You can head to the main page now.", reply_markup=reply_markup1)

    # Clear all existing data from context.user_data
    context.user_data.clear()

    return ConversationHandler.END  # End the conversation or navigate to another state


async def handle_reg_cancel(update, context):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("Okay..", callback_data='register')]
    ]
    reply_markup1 = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Sorry that you cancelled! Can we start over?", reply_markup=reply_markup1)

    # Clear all existing data from context.user_data
    context.user_data.clear()

    return ConversationHandler.END  # End the conversation


def store_new_user(user_data):
    # Function to store new user's Telegram ID and Username in the database
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            insert_query = """
                            INSERT INTO users (first_name, last_name, date_of_birth, photo, nric_number, moe_irs, mobile, postal, account_type, training_hours, telegram_id, telegram_handle)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """
            user_values = (user_data['first_name'], user_data['last_name'], user_data['date_of_birth'], user_data['photo'],
                           user_data['nric_number'], user_data['moe_irs'], user_data['mobile'],
                           user_data['postal'], 'standard', '0.00', user_data['telegram_id'],
                           user_data['telegram_username'])
            cursor.execute(insert_query, user_values)
            connection.commit()

        except Error as e:
            print("Error while inserting into MySQL", e)
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        print("Failed to connect to the database")


# GENERAL CANCEL CONVERSATION
async def cancel(update, context):
    await update.message.reply_text('Operation Cancelled.')
    return ConversationHandler.END


# CONVERSATION 2 - UPLOAD PROGRAMME - SCHOOL TO CONFIRM
async def start_addprog(update, context):
    query = update.callback_query
    await query.answer()

    # Check if the command is used in a group chat by a manager
    if query.message.chat.type not in ["group", "supergroup"]:
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="This can only be done in group chats.")
        return ConversationHandler.END

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Please enter the school name in full: eg. Halogen Secondary School")
    return SCHOOL


def is_user_manager(user_id):
    connection = create_db_connection()
    if connection is not None:
        try:
            with connection.cursor(buffered=True) as cursor:
                cursor.execute("SELECT account_type FROM users WHERE telegram_id = %s", (user_id,))
                result = cursor.fetchone()
                return result and result[0] == 'manager'
        except Error as e:
            print("Error while checking user role", e)
            return False
        finally:
            if connection.is_connected():
                connection.close()
    else:
        return False


async def school(update, context: CallbackContext):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    context.user_data["telegram_id"] = user_id
    context.user_data["chat_id"] = chat_id
    context.user_data['school'] = update.message.text
    await update.message.reply_text("Please enter the date of training (DDMMYY):")
    return PROG_DATE


async def prog_date(update, context: CallbackContext):
    progd_input = update.message.text
    # Parse date from DDMMYY format
    try:
        progd = datetime.strptime(progd_input, '%d%m%y')
        formatted_progd = progd.strftime('%Y-%m-%d')  # Convert to YYYY-MM-DD format
        context.user_data['prog_date'] = formatted_progd
        await update.message.reply_text(
            'What is the start time of this programme? Enter in 24 hour format (eg. 0730)')
        return START_TIME
    except ValueError:
        # Inform the user if the format is incorrect and ask them to re-enter the date
        await update.message.reply_text("Invalid date format. Please enter the programme date in DDMMYY format.")
        return PROG_DATE


async def start_time(update, context: CallbackContext):
    user_input_time = update.message.text
    parsed_starttime = datetime.strptime(user_input_time, "%H%M")
    mysql_time_format = parsed_starttime.strftime("%H:%M:%S")

    context.user_data['start_time'] = mysql_time_format
    await update.message.reply_text("How many hours is this session? Enter up to 2 decimal places.")
    return HOURS


async def hours(update, context: CallbackContext):
    context.user_data['hours'] = update.message.text
    await update.message.reply_text("What level is this? eg. P5, S3, J2")
    return STUDENT_LEVEL


async def student_level(update, context: CallbackContext):
    context.user_data['student_level'] = update.message.text
    await update.message.reply_text("How many trainers and facils do you need in total?")
    return TRAINERS_NEEDED


async def trainers_needed(update, context: CallbackContext):
    context.user_data['trainers_needed'] = update.message.text
    await update.message.reply_text("What is the name of this programme?")
    return PROGRAMME_NAME


async def programme_name(update, context: CallbackContext):
    context.user_data['programme_name'] = update.message.text

    # Converting date and time to readable formats
    prog_date_str = context.user_data['prog_date']
    start_time_str = context.user_data['start_time']
    prog_date_a = datetime.strptime(prog_date_str, '%Y-%m-%d')
    start_time_a = datetime.strptime(start_time_str, '%H:%M:%S')
    formatted_date = prog_date_a.strftime('%d %b %y')  # '04 Jan 23'
    formatted_time = start_time_a.strftime('%I:%M %p')  # '09:15 AM'

    # Assemble a summary of the collected data
    data_summary = (
        f"School: {context.user_data['school']}\n"
        f"Date: {formatted_date}\n"
        f"Time: {formatted_time}\n"
        f"Hours: {context.user_data['hours']}\n"
        f"Level: {context.user_data['student_level']}\n"
        f"Trainers Needed: {context.user_data['trainers_needed']}\n"
    )

    keyboard = [
        [InlineKeyboardButton("Confirm", callback_data='confirm_prog')],
        [InlineKeyboardButton("Cancel", callback_data='cancel_prog')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please review the programme details\n\n" + data_summary,
                                    reply_markup=reply_markup)

    return CONFIRM  # Which either goes to handle_reg_confirm or handle_reg_cancel


async def handle_prog_confirm(update, context):
    query = update.callback_query
    await query.answer()

    store_programme_data(context.user_data)

    await query.edit_message_reply_markup(reply_markup=None)
    keyboard = [
        [InlineKeyboardButton("View Programme ID", callback_data='view_prog_id')],
    ]
    reply_markup1 = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Programme added successfully.", reply_markup=reply_markup1)

    # Clear all existing data from context.user_data
    context.user_data.clear()

    return ConversationHandler.END  # End the conversation


async def handle_prog_cancel(update, context):
    query = update.callback_query
    await query.answer()

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Sorry something went wrong! Add a programme again under manager options.")

    # Clear all existing data from context.user_data
    context.user_data.clear()

    return ConversationHandler.END  # End the conversation


def store_programme_data(data):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            insert_query = """
            INSERT INTO jobs (uploader, chat_id, school, prog_date, start_time, hours, student_level, trainers_needed, job_status, programme_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (data['telegram_id'], data['chat_id'], data['school'],
                                          data['prog_date'], data['start_time'], data['hours'], data['student_level'],
                                          data['trainers_needed'], 'incomplete', data['programme_name']))
            connection.commit()

            # Retrieve the auto-generated session_id
            session_id = cursor.lastrowid
            print(f"Training Session ID number: {session_id}")  # Or use it as needed

        except Error as e:
            print("Error while inserting into MySQL", e)
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()


async def view_sesh_id(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = update.callback_query.message.chat_id

    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            query = """
            SELECT session_id FROM jobs 
            WHERE chat_id = %s
            """
            cursor.execute(query, (chat_id,))
            job = cursor.fetchone()

            if not job:
                return "No programme found. You sure it got added?"
            message_sesh_id = f"Programme ID: {job}"
            await context.bot.send_message(chat_id=chat_id, text=message_sesh_id)
            return
        except Error as e:
            return "Error while inserting into MySQL", e
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return "Failed to connect to the database."


# CONVERSATION 3 - LIST ALL JOBS - SELECT_DATE TO LIST_END
async def list_jobs(update, context):
    query = update.callback_query
    await query.answer()

    # Check if the command is used in a private chat
    if query.message.chat.type != 'private':
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="You can only do this in a direct message with Haley.")
        return ConversationHandler.END

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="I can show you all programmes within a 7-day period. Please let me know what is the first day to list from in DDMMYY format..")
    return SELECT_DATE


async def select_date(update, context):
    input_date = update.message.text
    try:
        # Convert DDMMYY to YYYY-MM-DD
        start_date = datetime.strptime(input_date, "%d%m%y")
        mysql_start_date = start_date.strftime("%Y-%m-%d")

        # Calculate the end date (7 days from the start date)
        end_date = start_date + timedelta(days=7)
        mysql_end_date = end_date.strftime("%Y-%m-%d")

        # Fetch jobs from the database
        message_select_date = fetch_jobs(mysql_start_date, mysql_end_date)
        keyboard = [
            [InlineKeyboardButton("Go to main page", callback_data='home')],
            [InlineKeyboardButton("Sign up for a programme", callback_data='signup')],
            [InlineKeyboardButton("Get a different list", callback_data='list')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message_select_date, reply_markup=reply_markup)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Invalid date format. Please use DDMMYY.")
        return SELECT_DATE


def fetch_jobs(start_date, end_date):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            query = """
            SELECT session_id, programme_name, school, prog_date, start_time, hours FROM jobs 
            WHERE prog_date BETWEEN %s AND %s AND trainers_needed > 0
            """
            cursor.execute(query, (start_date, end_date))
            jobs = cursor.fetchall()

            if not jobs:
                return "No programmes found in the specified period."

            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            formatted_start_date = start_date_obj.strftime('%d %b %y')
            formatted_end_date = end_date_obj.strftime('%d %b %y')
            message_fetch_jobs = f"Programmes from {formatted_start_date} to {formatted_end_date}:\n\n"
            for job in jobs:
                # Check if job[4] is a timedelta object and format it
                formatted_time_b = (datetime.min + job[4]).strftime('%I:%M %p') if isinstance(job[4], timedelta) else str(job[4])
                message_fetch_jobs += f"ID Number: {job[0]}\n\t• Programme: {job[1]}\n\t• School: {job[2]}\n\t• Date: {job[3].strftime('%d %b %y')}\n\t• Time: {formatted_time_b}\n\t• Hours: {job[5]}\n\n"
            return message_fetch_jobs

        except Error as e:
            return "Error retrieving programmes.", e
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return "Failed to connect to the database."


# CONVERSATION 4 - APPLYING FOR JOB - APPLY_JOB TO ANOTHER_JOB
async def apply_job_handler(update, context):
    query = update.callback_query
    await query.answer()

    # Check if the command is used in a private chat
    if query.message.chat.type != 'private':
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id,
                                       text="You can only do this in a direct message with Haley.")
        return ConversationHandler.END

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Please enter the ID Number of the programme you wish to sign up for.")
    return APPLY_JOB


async def apply_job(update, context):
    session_id = update.message.text

    # Check if the job exists and if the user has already applied
    if not job_exists(session_id):
        await update.message.reply_text("This ID is invalid. Please enter a valid programme ID number.")
        return APPLY_JOB

    # Show job details for user to confirm
    message_job_check = fetch_one_job(session_id)
    await update.message.reply_text("Please confirm that this is the programme you are signing up for")
    await update.message.reply_text(message_job_check)
    await update.message.reply_text("If this is correct, please enter the ID Number again. If not, /cancel and start over.")
    context.user_data['app_session_id'] = session_id
    return CONFIRM_APPLY


def job_exists(session_id):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM jobs WHERE session_id = %s", (session_id,))
            (count,) = cursor.fetchone()
            return count > 0
        except Error as e:
            print("Error while checking programme status", e)
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return False


def fetch_one_job(session_id):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            query = """
            SELECT programme_name, school, prog_date, start_time, hours FROM jobs 
            WHERE session_id = %s
            """
            cursor.execute(query, (session_id,))
            job = cursor.fetchone()

            if not job:
                return "No programme found with the provided Session ID."
            programme, school, prog_date, start_time, hours = job
            # Check if job[4] is a timedelta object and format it
            formatted_time_c = (datetime.min + start_time).strftime('%I:%M %p') if isinstance(start_time, timedelta) else str(start_time)
            message_fetch_job = f"Programme: {programme}\nSchool: {school}\nDate: {prog_date.strftime('%d-%m-%y')}\nTime: {formatted_time_c}\nHours: {hours}\n"
            return message_fetch_job
        except Error as e:
            return "Error retrieving programme details.", e
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return "Failed to connect to the database."


async def confirm_apply(update, context):
    telegram_id = update.message.from_user.id
    session_id = update.message.text

    if session_id != context.user_data['app_session_id']:
        await update.message.reply_text("You keyed in the wrong ID number. Please enter the ID number again.")
        return CONFIRM_APPLY

    # Check if the application exists (the user has already applied)
    if app_exists(telegram_id, session_id):
        await update.message.reply_text("You have already signed up for this programme.")
        # Clear all existing data from context.user_data
        context.user_data.clear()
        return ConversationHandler.END

    # Enter the application into the database
    insert_app(telegram_id, session_id)

    # Ask if they want to sign up for another
    keyboard = [
        [InlineKeyboardButton("Yes", callback_data='confirm_another')],
        [InlineKeyboardButton("No", callback_data='cancel_another')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Sign up successfully sent. Would you like to sign up for another?", reply_markup=reply_markup)
    return ANOTHER_JOB


def app_exists(telegram_id, session_id):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            query = """
                    SELECT COUNT(*) 
                    FROM applications 
                    WHERE telegram_id = %s 
                    AND session = %s 
                    AND app_status NOT IN ('accepted', 'pending')
                    """
            cursor.execute(query, (telegram_id, session_id,))
            (count,) = cursor.fetchone()
            return count > 0
        except Error as e:
            print("Error while checking application status", e)
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return False


def insert_app(telegram_id, session_id):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            cursor.execute("SET time_zone = '+08:00';")
            insert_query = """
                INSERT INTO applications (uid, telegram_id, session_id, chat_id, first_name, last_name, mobile, postal, programme_name, school, prog_date, start_time, hours, student_level, app_status, apply_time)
                SELECT 
                    u.uid, 
                    u.telegram_id, 
                    j.session_id, 
                    j.chat_id, 
                    u.first_name, 
                    u.last_name, 
                    u.mobile, 
                    u.postal, 
                    j.programme_name, 
                    j.school, 
                    j.prog_date, 
                    j.start_time, 
                    j.hours, 
                    j.student_level, 
                    'pending', 
                    NOW()
                FROM 
                    users u
                JOIN 
                    jobs j ON j.session_id = %s
                WHERE 
                    u.telegram_id = %s;
                """
            cursor.execute(insert_query, (session_id, telegram_id))
            connection.commit()
        except Error as e:
            print("Error while saving signup. Please check in with Halogen!", e)
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()


async def handle_another_confirm(update, context):
    query = update.callback_query
    await query.answer()

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Please enter the ID number of the Programme you wish to sign up for.")

    # Clear all existing data from context.user_data
    context.user_data.clear()

    return APPLY_JOB


async def handle_another_cancel(update, context):
    query = update.callback_query
    await query.answer()

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Thanks! You should get an update soon.")

    # Clear all existing data from context.user_data
    context.user_data.clear()

    return ConversationHandler.END  # End the conversation


# CONVERSATION 5 - VIEW APPLICATIONS FOR A GIVEN CHAT GROUP
async def view_applications(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = update.callback_query.message.chat_id

    # Check if the command is used in a group chat by a manager
    if query.message.chat.type not in ["group", "supergroup"]:
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="This can only be done in group chats.")
        return

    # Query the database
    message_viewapp = fetch_apps(chat_id)
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text=message_viewapp)

    keyboard = [
        [InlineKeyboardButton("Accept applicants", callback_data='accept_app')],
        [InlineKeyboardButton("Reject applicants", callback_data='reject_app')],
    ]
    reply_markup1 = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Click on either option to accept or reject associates.", reply_markup=reply_markup1)
    return ACCEPT_OR_REJECT


def fetch_apps(chat_id):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            query = """
                    SELECT uid, first_name, last_name, postal 
                    FROM applications 
                    WHERE chat_id = %s AND app_status = 'pending'
                    """
            cursor.execute(query, (chat_id,))
            applications = cursor.fetchall()

            if not applications:
                return "No applications yet."

            applications_info = f"Applications:\n\n"
            for app in applications:
                applications_info += f"UID: {app[0]}\n\t• Name: {app[1]} {app[2]}\n\t• Postal: {app[3]}\n\n"
            return applications_info

        except Error as e:
            return "Error retrieving application details.", e
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return "Failed to connect to the database."


#  COMMAND - ACCEPT APPLICATIONS
async def app_accept_button(update, context):
    query = update.callback_query
    await query.answer()

    user_id = update.callback_query.from_user.id

    # Check if the command is used in a group chat by a manager
    if query.message.chat.type not in ["group", "supergroup"]:
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="This can only be done in group chats.")
        return

    # Verify if the user is a manager
    if not is_user_manager(user_id):
        await context.bot.send_message(chat_id=query.message.chat_id, text="You must be a manager to use this command.")
        return

    # Store chat_id in context.user_data
    context.user_data['chat_id'] = query.message.chat_id

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Please enter the UIDs of the associates you want to accept. (eg. 23, 45, 67)")
    return PROCESS_ACCEPT


async def accept_applicants(update, context):
    chat_id = context.user_data.get('chat_id')

    # Check if the update contains a message and text
    if not (update.message and update.message.text):
        await update.message.reply_text("Please enter the UIDs.")
        return PROCESS_ACCEPT

    # Extract UIDs from the message text
    try:
        user_input = update.message.text
        uids = [uid.strip() for uid in user_input.split(',') if uid.strip().isdigit()]

        if not uids:
            raise ValueError("No valid UIDs provided. Usage: <UID1>, <UID2>, <UID3>")

        # Convert UIDs to integers
        uids = [int(uid) for uid in uids]

    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    # Determine number of UIDs accepted
    num_accepted = len(uids)
    update_trainers_subtract(chat_id, num_accepted)

    # Update the database and send notifications
    for uid in uids:
        await update_accept_application(bot, chat_id, uid)

    await context.bot.send_message(chat_id=chat_id, text="Applicant(s) have been accepted.")
    # Clear all existing data from context.user_data
    context.user_data.clear()
    return ConversationHandler.END


def update_trainers_subtract(chat_id, num_accepted):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            query = """
                    UPDATE jobs
                    SET trainers_needed = trainers_needed - %s
                    WHERE chat_id = %s
                    """
            cursor.execute(query, (num_accepted, chat_id))
            connection.commit()
        except mysql.connector.Error as e:
            print(f"Error updating trainers_needed: {e}")
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()


async def update_accept_application(bot, chat_id, uid):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            # Update application status
            cursor = connection.cursor()
            query = """
                    UPDATE applications
                    SET app_status = 'accepted'
                    WHERE chat_id = %s 
                    AND uid = %s 
                    AND app_status = 'pending'
                    """
            cursor.execute(query, (chat_id, uid))
            connection.commit()

            # Retrieve application data
            select_query = """
                                           SELECT programme_name, school, prog_date, start_time, hours, telegram_id
                                           FROM applications
                                           WHERE chat_id = %s AND uid = %s
                                           """
            cursor.execute(select_query, (chat_id, uid))
            result = cursor.fetchone()

            if result:
                programme_name, school, prog_date, start_time, hours, telegram_id = result

                # Export Telegram group invite link
                try:
                    join_link = await bot.export_chat_invite_link(chat_id)
                except Exception as e:
                    logging.error(f"Error exporting chat invite link: {e}")
                    join_link = "Unavailable"

                # Send a direct message
                formatted_time_f = (datetime.min + start_time).strftime('%I:%M %p') if isinstance(start_time, timedelta) else str(start_time)
                message = f"Good news! You have been confirmed for {programme_name} at {school} on {prog_date.strftime('%d-%m-%y')} starting at {formatted_time_f} for {hours} hours. Please click the link to join the programme chat group:\n{join_link}"
                await bot.send_message(chat_id=telegram_id, text=message)
            else:
                logging.warning("No matching record found")

        except mysql.connector.Error as e:
            print(f"Error updating application statuses: {e}")
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()


#  COMMAND - REJECT APPLICATIONS
async def app_reject_button(update, context):
    query = update.callback_query
    await query.answer()

    user_id = update.callback_query.from_user.id

    # Check if the command is used in a group chat by a manager
    if query.message.chat.type not in ["group", "supergroup"]:
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="This can only be done in group chats.")
        return

    # Verify if the user is a manager
    if not is_user_manager(user_id):
        await context.bot.send_message(chat_id=query.message.chat_id, text="You must be a manager to use this command.")
        return

    # Store chat_id in context.user_data
    context.user_data['chat_id'] = query.message.chat_id

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Please enter the UIDs of the associates you want to reject. (eg. 23, 45, 67)")
    return PROCESS_REJECT


async def reject_applicants(update, context):
    chat_id = context.user_data.get('chat_id')
    user_input = update.message.text

    # Check if the update contains a message and text
    if not (update.message and update.message.text):
        await update.message.reply_text("Please enter the UIDs.")
        return

    # Extract UIDs from the message text
    try:
        uids = [uid.strip() for uid in user_input.split(',') if uid.strip().isdigit()]

        if not uids:
            raise ValueError("No valid UIDs provided. Usage: <UID1>, <UID2>, <UID3>")

        # Convert UIDs to integers
        uids = [int(uid) for uid in uids]

    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    # Update the database and send notifications
    for uid in uids:
        update_reject_application(bot, chat_id, uid)

    await context.bot.send_message(chat_id=chat_id, text="Applicant(s) have been rejected.")
    # Clear all existing data from context.user_data
    context.user_data.clear()
    return ConversationHandler.END


def update_reject_application(bot, chat_id, uid):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            # Update application status
            cursor = connection.cursor()
            query = """
                    UPDATE applications
                    SET app_status = 'rejected'
                    WHERE chat_id = %s 
                    AND uid = %s 
                    AND app_status = 'pending'
                    """
            cursor.execute(query, (chat_id, uid))
            connection.commit()

            # Retrieve application data
            select_query = """
                                           SELECT programme_name, school, prog_date, start_time, telegram_id
                                           FROM applications
                                           WHERE chat_id = %s AND uid = %s
                                           """
            cursor.execute(select_query, (chat_id, uid))
            result = cursor.fetchone()

            if result:
                programme_name, school, prog_date, start_time, telegram_id = result

                # Send a direct message
                formatted_time_e = (datetime.min + start_time).strftime('%I:%M %p') if isinstance(start_time, timedelta) else str(start_time)
                message = f"Hello! For {programme_name} at {school} on {prog_date.strftime('%d-%m-%y')} starting at {formatted_time_e}, the programme is full and you will not be involved. Thanks for signing up and I hope we get to do the next one!"
                bot.send_message(chat_id=telegram_id, text=message)
            else:
                logging.warning("No matching record found")

        except mysql.connector.Error as e:
            print(f"Error updating application statuses: {e}")
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()


# CONVERSATION 6 - USER VIEWING THEIR OWN APPLICATIONS PERHAPS WITHDRAWING
async def view_user_apps(update, context):
    query = update.callback_query
    await query.answer()

    # Check if the command is used in a private chat
    if query.message.chat.type != 'private':
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id,
                                       text="You can only do this in a direct message with Haley.")
        return ConversationHandler.END

    user_id = query.from_user.id
    applications = fetch_user_applications(user_id)  # Fetch applications from DB
    await context.bot.send_message(chat_id=query.message.chat_id, text=applications)

    # Display options to the user
    keyboard = [
        [InlineKeyboardButton("Nope all good", callback_data='go_home1')],
        [InlineKeyboardButton("Withdraw from Programme", callback_data='withdraw')],
    ]
    reply_markup1 = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Anything else?", reply_markup=reply_markup1)
    return USER_OPTIONS  # Going either to home or withdraw


def fetch_user_applications(user_id):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            query = """
                    SELECT session_id, programme_name, school, prog_date, start_time, hours, app_status
                    FROM applications
                    WHERE telegram_id = %s AND app_status IN ('accepted', 'pending')
                    """
            cursor.execute(query, (user_id,))
            applications = cursor.fetchall()

            if not applications:
                return "You have no applications."

            applications_info = "Your Programmes:\n\n"
            for app in applications:
                session_id, programme_name, school, prog_date, start_time, hours, app_status = app
                formatted_time_d = (datetime.min + start_time).strftime('%I:%M %p') if isinstance(start_time, timedelta) else str(start_time)
                applications_info += f"ID Number: {session_id}\n\t• Programme: {programme_name}\n\t• School: {school}\n\t• Date: {prog_date.strftime('%d-%m-%y')}\n\t• Time: {formatted_time_d}\n\t• Hours: {hours}\n\t• Status: {app_status}\n\n"
            return applications_info

        except mysql.connector.Error as e:
            return f"Error retrieving applications: {e}"
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return "Failed to connect to the database."


async def handle_go_home(update, context):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("List all programmes", callback_data='list')],
        [InlineKeyboardButton("Sign up for a programme", callback_data='signup')],
        [InlineKeyboardButton("Profile", callback_data='profile')],
        [InlineKeyboardButton("Manage Sign Ups", callback_data='myprog')],
        [InlineKeyboardButton("Help", callback_data='help')],
    ]
    reply_markup1 = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Okay!", reply_markup=reply_markup1)
    return ConversationHandler.END


async def handle_withdraw(update, context):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("Yes sadly", callback_data='yes_withdraw')],
        [InlineKeyboardButton("No lol kidding", callback_data='go_home2')],
    ]
    reply_markup1 = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text("whyyyyy - you serious?", reply_markup=reply_markup1)
    return WITHDRAW_CONFIRMATION


async def handle_cfm_withdraw(update, context):
    query = update.callback_query
    await query.answer()

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Sigh okay - what is the Programme ID of the session you want to withdraw from?")
    return ENTER_PROGRAMME_ID


async def handle_walau(update, context):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("List all programmes", callback_data='list')],
        [InlineKeyboardButton("Sign up for a programme", callback_data='signup')],
        [InlineKeyboardButton("Profile", callback_data='profile')],
        [InlineKeyboardButton("Manage Sign Ups", callback_data='myprog')],
        [InlineKeyboardButton("Help", callback_data='help')],
    ]
    reply_markup1 = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Wah don't liddat play leh", reply_markup=reply_markup1)
    return ConversationHandler.END


async def withdrawing_app(update, context):
    session_id = update.message.text
    user_id = update.message.from_user.id

    # Show application details for user to confirm
    message_app_check = fetch_one_app(session_id, user_id)
    await update.message.reply_text("Please confirm that this is the programme you are withdrawing from.")
    await update.message.reply_text(message_app_check)
    await update.message.reply_text("If this is correct, please enter the ID Number again. If not, /cancel and start over.")
    context.user_data['wd_session_id'] = session_id
    return CONFIRM_WITHDRAWAL


def fetch_one_app(session_id, user_id):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            query = """
            SELECT programme_name, school, prog_date, start_time, hours FROM applications 
            WHERE session_id = %s AND telegram_id = %s
            """
            cursor.execute(query, (session_id, user_id))
            job = cursor.fetchone()

            if not job:
                return "Ah wait there is no signup with this ID though."
            programme, school, prog_date, start_time, hours = job
            # Check if job[4] is a timedelta object and format it
            formatted_time_g = (datetime.min + start_time).strftime('%I:%M %p') if isinstance(start_time, timedelta) else str(start_time)
            message_fetch_job = f"Programme: {programme}\nSchool: {school}\nDate: {prog_date.strftime('%d-%m-%y')}\nTime: {formatted_time_g}\nHours: {hours}\n"
            return message_fetch_job
        except Error as e:
            return "Error retrieving programme details.", e
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return "Failed to connect to the database."


async def confirm_withdraw(update, context):
    telegram_id = update.message.from_user.id
    session_id = update.message.text

    if session_id != context.user_data['wd_session_id']:
        await update.message.reply_text("You keyed in the wrong ID number. Please enter the ID number again.")
        return CONFIRM_WITHDRAWAL

    # Edit the application in the database
    await withdraw_application_accepted(session_id, telegram_id)

    # Send them back to list
    keyboard = [
        [InlineKeyboardButton("Main Page", callback_data='home')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Withdraw successful. Sad to see you go!", reply_markup=reply_markup)
    # Clear all existing data from context.user_data
    context.user_data.clear()
    return ConversationHandler.END


async def withdraw_application_accepted(session_id, telegram_id):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()

            # Check if there is an accepted application first
            select_query = "SELECT session_id FROM applications WHERE session_id = %s AND telegram_id = %s AND app_status = 'accepted'"
            cursor.execute(select_query, (session_id, telegram_id))
            temp_sesh_id_result = cursor.fetchone()

            if temp_sesh_id_result:
                temp_sesh_id = temp_sesh_id_result[0]

                # Update the trainers_needed field in the jobs table for accepted applications
                update_app_query = "UPDATE jobs SET trainers_needed = trainers_needed + 1 WHERE session_id = %s"
                cursor.execute(update_app_query, (temp_sesh_id,))

            # Update the application status to 'withdrawn' for both accepted and pending applications
            update_query = "UPDATE applications SET app_status = 'withdrawn' WHERE session_id = %s AND telegram_id = %s"
            cursor.execute(update_query, (session_id, telegram_id))

            connection.commit()

            if temp_sesh_id_result:
                temp_sesh_id = temp_sesh_id_result[0]

                # Select the chat_id from the session_id
                select_query = "SELECT chat_id, first_name, last_name, uid FROM applications WHERE session_id = %s AND telegram_id = %s"
                cursor.execute(select_query, (temp_sesh_id, telegram_id))
                temp_results = cursor.fetchone()

                chat_id, first_name, last_name, uid = temp_results

                # Send a message into chat
                temp_chat_id = chat_id
                message = f"Bad news, someone dropped out: {first_name} {last_name} (ID: {uid}). Applications open again."
                await bot.send_message(chat_id=temp_chat_id, text=message)

                return "Application withdrawn and trainers_needed updated."
            else:
                return "Application withdrawn."

        except mysql.connector.Error as e:
            return f"Error in processing withdrawal: {e}"
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return "Failed to connect to the database."


# COMMAND - MANAGER VIEWS PHOTO
async def send_user_photo(update, context):
    # Check if the command is used in a private chat
    if update.message.chat.type != 'private':
        await update.message.reply_text("This command can only be used in private messages.")
        return

    user_id = update.message.from_user.id

    # Verify if the user is a manager
    if not is_user_manager(user_id):
        await context.bot.send_message(chat_id=user_id, text="You must be a manager to use this command.")
        return

    # Extract user ID from the admin user input
    try:
        args = context.args
        if not args or not args[0].isdigit():
            raise ValueError
        u_id = args[0]
    except ValueError:
        await update.message.reply_text("Usage: /seephoto <ID Number>")
        return

    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            query = "SELECT photo FROM users WHERE uid = %s"
            cursor.execute(query, (u_id,))
            photo_result = cursor.fetchone()

            if photo_result and photo_result[0]:
                await context.bot.send_photo(chat_id=user_id, photo=photo_result[0])
            else:
                await context.bot.send_message(chat_id=user_id, text="No photo found.")
        except mysql.connector.Error as e:
            await context.bot.send_message(chat_id=user_id, text=f"Error retrieving photo: {e}")
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()


# CONVERSATION 7 - COMPLETING A PROGRAMME
async def complete_prog(update, context):
    query = update.callback_query
    await query.answer()

    # Check if the command is used in a group chat by a manager
    if query.message.chat.type not in ["group", "supergroup"]:
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=query.message.chat_id, text="This can only be done in group chats.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Yes this programme is done", callback_data='yes_complete')],
        [InlineKeyboardButton("Not yet, my bad", callback_data='no_incomplete')],
    ]
    reply_markup1 = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text="Is this programme finished? By completing the programme you will lock in all trainers, payments, and hours.",
                                   reply_markup=reply_markup1)
    return COMPLETE_OR_CANCEL


async def yes_complete_handle(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = update.callback_query.message.chat_id
    message_trainer_check = fetch_trainers(chat_id)

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Okay! Great job team! Let me confirm: Which of these persons were NOT in the programme? (Enter their ID numbers; 0 if none)")
    await context.bot.send_message(chat_id=query.message.chat_id, text=message_trainer_check)
    return ANY_REMOVALS


def fetch_trainers(chat_id):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()
            query = """
            SELECT first_name, last_name, uid FROM applications 
            WHERE chat_id = %s AND app_status = 'accepted' 
            """
            cursor.execute(query, (chat_id,))
            trainers = cursor.fetchall()

            if not trainers:
                return "No trainers confirmed for this programme."

            message_fetch_trainers = f"Listing all persons:\n\n"
            for trainer in trainers:
                message_fetch_trainers += f"• {trainer[0]} {trainer[1]} ({trainer[2]})\n\n"
            return message_fetch_trainers

        except Error as e:
            return "Error retrieving list of associates.", e
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return "Failed to connect to the database."


async def no_incomplete_handle(update, context):
    query = update.callback_query
    await query.answer()

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Heh okay let me know when it's done!")
    return ConversationHandler.END


async def trainer_removals(update, context):
    chat_id = update.message.chat_id

    # Check if the update contains a message and text
    if not (update.message and update.message.text):
        await update.message.reply_text("Please enter the UIDs.")
        return

    # Extract UIDs from the message text
    try:
        user_input = update.message.text
        uids = [uid.strip() for uid in user_input.split(',') if uid.strip().isdigit()]

        if not uids:
            raise ValueError("No valid UIDs provided. Usage: <UID1>, <UID2>, <UID3>")

        # Check if the user input is only '0'
        if uids == ['0']:
            await update.message.reply_text("Okay no changes made!")
            keyboard = [
                [InlineKeyboardButton("Confirm list", callback_data='double_confirm_list')],
                [InlineKeyboardButton("Made an oops, need to do again", callback_data='start_over')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=chat_id,
                                           text="Confirm that the trainer list is correct? If so confirm, if not start over.",
                                           reply_markup=reply_markup)
            return CONFIRM_ALL_PROG_DEETS

        # Convert UIDs to integers
        uids = [int(uid) for uid in uids]

    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    # Update the database
    for uid in uids:
        update_completed_accepts_to_removed(chat_id, uid)

    await update.message.reply_text("Records have been updated. Check one more time?")
    message_trainer_check2 = fetch_trainers(chat_id)
    await update.message.reply_text(message_trainer_check2)
    keyboard = [
        [InlineKeyboardButton("Confirm list", callback_data='double_confirm_list')],
        [InlineKeyboardButton("Made an oops, need to do again", callback_data='start_over')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text="All correct? If so confirm, if not start over.", reply_markup=reply_markup)
    return CONFIRM_ALL_PROG_DEETS


def update_completed_accepts_to_removed(chat_id, uid):
    connection = create_db_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        update_query = "UPDATE applications SET app_status = 'removed' WHERE chat_id = %s AND uid = %s"
        cursor.execute(update_query, (chat_id, uid))
        connection.commit()
    except Error as e:
        print(f"Error updating job status: {e}")
    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


async def completion_confirm_button(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = update.callback_query.message.chat_id

    update_training_hours(chat_id)

    update_job_status(chat_id)

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="All done! Training hours updated and programme closed.")
    return ConversationHandler.END


def update_training_hours(chat_id):
    connection = create_db_connection()
    cursor = None
    if connection is not None:
        try:
            cursor = connection.cursor()

            # (1) Select uids from applications table
            select_uids_query = """
                SELECT uid FROM applications 
                WHERE chat_id = %s AND app_status = 'accepted'
            """
            cursor.execute(select_uids_query, (chat_id,))
            uids = [item[0] for item in cursor.fetchall()]

            if not uids:
                return "No UIDs found from SQLapps, please check with Tim on this error."

            # (2) Select hours from jobs table
            select_hours_query = """
                SELECT hours FROM jobs 
                WHERE chat_id = %s
            """
            cursor.execute(select_hours_query, (chat_id,))
            hours_result = cursor.fetchone()
            if hours_result:
                hours = hours_result[0]
            else:
                return "No hours found from SQLjobs, please check with Tim on this error."

            # (3) Update training_hours in users table
            for uid in uids:
                update_hours_query = """
                    UPDATE users 
                    SET training_hours = training_hours + %s 
                    WHERE uid = %s
                """
                cursor.execute(update_hours_query, (hours, uid))

            connection.commit()
            return "Training hours updated successfully."

        except Error as e:
            return f"Error updating training hours: {e}"
        finally:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
    else:
        return "Failed to connect to the database."


def update_job_status(chat_id):
    connection = create_db_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        update_query = "UPDATE jobs SET job_status = 'complete' WHERE chat_id = %s"
        cursor.execute(update_query, (chat_id,))
        connection.commit()
    except Error as e:
        print(f"Error updating job status: {e}")
    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


async def start_over_complete(update, context):
    query = update.callback_query
    await query.answer()

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Alright - start again from the manager home!")
    return ConversationHandler.END


# DM default message
async def default_response(update, context):
    keyboard = [
        [InlineKeyboardButton("Show me", callback_data='home')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Hey there! Click the button to see how I can help.", reply_markup=reply_markup)


# MAIN BOT FUNCTION
def main():
    application = Application.builder().token(TOKEN).build()

    # Add Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler('setrole', set_user_role))
    application.add_handler(CommandHandler('managerisme', manager_home))
    application.add_handler(CommandHandler('seephoto', send_user_photo))

    # Add Conversation Handlers (Commands below)
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(register, pattern='^register$')],
        states={
            FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, first_name_handler)],
            LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, last_name_handler)],
            DATE_OF_BIRTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, date_of_birth_handler)],
            PHOTO_UPLOAD: [MessageHandler(filters.PHOTO, photo_handler)],
            NRIC_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, nric_number_handler)],
            MOE_IRS: [MessageHandler(filters.TEXT & ~filters.COMMAND, moe_irs_handler)],
            MOBILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, mobile_handler)],
            POSTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, postal_handler)],
            LOCKREG: [
                CallbackQueryHandler(handle_reg_confirm, pattern='^confirm_reg$'),
                CallbackQueryHandler(handle_reg_cancel, pattern='^cancel_reg$')
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    addprog_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_addprog, pattern='^add_prog$')],
        states={
            SCHOOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, school)],
            PROG_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, prog_date)],
            START_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_time)],
            HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, hours)],
            STUDENT_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_level)],
            TRAINERS_NEEDED: [MessageHandler(filters.TEXT & ~filters.COMMAND, trainers_needed)],
            PROGRAMME_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, programme_name)],
            CONFIRM: [
                CallbackQueryHandler(handle_prog_confirm, pattern='^confirm_prog$'),
                CallbackQueryHandler(handle_prog_cancel, pattern='^cancel_prog$')
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    joblist_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(list_jobs, pattern='^list$')],
        states={
            SELECT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_date)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    applications_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(view_applications, pattern='^view_app$')],
        states={
            ACCEPT_OR_REJECT: [CallbackQueryHandler(app_accept_button, pattern='^accept_app$'),
                               CallbackQueryHandler(app_reject_button, pattern='^reject_app$')],
            PROCESS_ACCEPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, accept_applicants)],
            PROCESS_REJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_applicants)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    signup_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(apply_job_handler, pattern='^signup$')],
        states={
            APPLY_JOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_job)],
            CONFIRM_APPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_apply)],
            ANOTHER_JOB: [
                CallbackQueryHandler(handle_another_confirm, pattern='^confirm_another$'),
                CallbackQueryHandler(handle_another_cancel, pattern='^cancel_another$')
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    user_view_apps_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(view_user_apps, pattern='^myprog$')],
        states={
            USER_OPTIONS: [CallbackQueryHandler(handle_go_home, pattern='^go_home1$'),
                           CallbackQueryHandler(handle_withdraw, pattern='^withdraw$')],
            WITHDRAW_CONFIRMATION: [CallbackQueryHandler(handle_cfm_withdraw, pattern='^yes_withdraw$'),
                                    CallbackQueryHandler(handle_walau, pattern='^go_home2$')],
            ENTER_PROGRAMME_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdrawing_app)],
            CONFIRM_WITHDRAWAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_withdraw)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    completions_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(complete_prog, pattern='^complete_programme$')],
        states={
            COMPLETE_OR_CANCEL: [CallbackQueryHandler(yes_complete_handle, pattern='^yes_complete$'),
                                 CallbackQueryHandler(no_incomplete_handle, pattern='^no_incomplete$')],
            ANY_REMOVALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, trainer_removals)],
            CONFIRM_ALL_PROG_DEETS: [CallbackQueryHandler(completion_confirm_button, pattern='^double_confirm_list$'),
                                     CallbackQueryHandler(start_over_complete, pattern='^start_over$')],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Add Conversation Commands
    application.add_handler(conv_handler)
    application.add_handler(addprog_handler)
    application.add_handler(joblist_handler)
    application.add_handler(applications_handler)
    application.add_handler(signup_handler)
    application.add_handler(user_view_apps_handler)
    application.add_handler(completions_handler)

    # Add CallbackQueryHandler for handling inline keyboard interactions
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Add default message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, default_response))

    # Start the bot
    application.run_polling()


if __name__ == '__main__':
    main()
