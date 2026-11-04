"""
SMTAFE Class Attendance Tracking System

Author: Joshua King
Date: 23/02/2026
Version: 1.0
"""

# We use the following built-in libraries
import datetime
import os.path

bold_red_on = "\x1b[1;31m"
bold_green_on = "\x1b[1;32m"
italic_yellow_on = "\x1b[3;33m"
bold_underline_magenta_on = "\x1b[1;4;35m"
blue_on = "\x1b[34m"
all_off = "\x1b[0m"


def print_title(title="SMTAFE Class and Attendance Tracker"):
    print(bold_underline_magenta_on, title, all_off)


def print_error(text):
    print(bold_red_on, text, all_off)


def print_bad(text):
    print_error("❌ " + text)


def print_good(text):
    print(bold_green_on, "✔️", text, all_off)


def print_student(name):
    print("🧑‍🎓", italic_yellow_on, name)


def print_students(students, class_name="this class"):
    print_title("Students in " + class_name)
    for student in students:
        print_student(student)


def open_class(name):
    students = []
    if os.path.exists(name + ".txt"):
        with open(name + ".txt", "rt") as f:
            students = [name.strip() for name in f]
        print_students(students)
    else:
        print_error(f"Class {name} not found")
    return students


def save_class(name, students):
    with open(name + ".txt", "wt") as f:
        for student in students:
            f.write(student + "\n")


def ask_for_text_input(prompt):
    print(blue_on)
    value = input(prompt + "\n")
    print(all_off)
    return value


def ask_for_int_input(prompt, first=0, last=-1):
    while True:
        print(blue_on)
        value = input(prompt + "\n")
        if not value.isnumeric():
            print_error("Please enter a number!")
        elif int(value) < first:
            print_error(f"Please enter a number ≥ {first}")
        elif last >= 0 and int(value) > last:
            print_error(f"Please enter a number ≤ {last}")
        else:
            print(all_off)
            break
    return int(value)


def ask_for_yesno_input(prompt):
    while True:
        print(blue_on)
        value = input(prompt + "\n").lower()[0]
        if value == "y":
            print(all_off)
            return True
        elif value == "n":
            print(all_off)
            return False
        else:
            print_error("Please enter yes or no!")


def ask_for_menu(prompt, options):
    emoji_numbers = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
    print_title(prompt)
    print(blue_on)
    for i in range(len(options)):
        print(emoji_numbers[i + 1], options[i])
    print(emoji_numbers[0], "Exit")
    return ask_for_int_input("Make a selection", 0, len(options))


def ask_for_selection(prompt, options):
    print_title(prompt)
    print(blue_on)
    print(0, "➡️", "Cancel")
    for i in range(len(options)):
        print(i + 1, "⬅️➡️", options[i])
    while True:
        value = ask_for_text_input("Make a selection")
        if value.strip() in options:
            return options.index(value.strip()) + 1
        elif value.isnumeric() and int(value) <= len(options):
            return int(value)
        print_error("Please try again.")


print_title()

# Ask user for the class name
class_name = ask_for_text_input("Which class is this?")

# Create an empty list to hold the students
students = open_class(class_name)

while True:
    options = ["Add Students", "Show Students", "Delete Students"]
    if len(students) > 0:
        option = ask_for_menu("Updating " + class_name, options)
    else:
        option = 1
    if option == 0:
        break
    elif options[option - 1] == "Add Students":
        while True:
            student = ask_for_text_input("What is the student's name (empty to stop)?")
            if len(student.strip()) == 0:
                break
            students.append(student)
    elif options[option - 1] == "Show Students":
        print_students(students)
    elif options[option - 1] == "Delete Students":
        while len(students) > 0:
            student = ask_for_selection(
                "Select a student to delete by name or number", students
            )
            if student > 0:
                print_error("Goodbye " + students[student - 1])
                del students[student - 1]
            else:
                break

save_class(class_name, students)

print_title("Please Take Attendance Now!")

here = []
# Ask the user if each student is here or not
for name in students:
    # If the user enters something starting with Y or y consider the student here
    if ask_for_yesno_input("Is " + name + " here?"):
        here.append(name)

if len(students) > 0:
    print_good("There are " + str(len(students)) + " in the " + class_name + " class")
    if len(here) < len(students):
        print_bad(
            f"Only {len(here)} students ({int(100.0 * len(here) / len(students))}%) here today"
        )
        for name in students:
            if name in here:
                print_good(name)
            else:
                print_bad(name)
    else:
        print_good("All students are here today")

# Append to the log so we do not lose our past attendance
now = str(datetime.datetime.now())
with open(class_name + ".log", "at") as f:
    # Write the current time
    f.write(now)
    # Write each student that was here, separated by commas, don't write a new line yet!
    for name in here:
        f.write("," + name)
    # Finish the line, notice that write doesn't do one by itself (print does)
    f.write("\n")
print("⌚ Attendance logged for " + now)
