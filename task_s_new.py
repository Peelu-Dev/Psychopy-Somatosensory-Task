

from psychopy import visual, core, event, gui, data
import random, os
import subprocess
from pylsl import StreamInfo, StreamOutlet, local_clock, resolve_stream, StreamInlet
import time
from datetime import datetime
import numpy as np
import pandas as pd
from pathlib import Path 
import pylsl
import argparse
import csv
import itertools
import logging
import sys

from ds8r import DS8R


original_popen = subprocess.Popen

def popen_without_window(*args, **kwargs):
    # Ensure startupinfo is set to hide window
    if sys.platform == 'win32':
        startupinfo = kwargs.get('startupinfo', subprocess.STARTUPINFO())
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs['startupinfo'] = startupinfo
        shell=True
        
        # Redirect stdout and stderr to prevent command window
        if 'stdout' not in kwargs:
            kwargs['stdout'] = subprocess.PIPE
        if 'stderr' not in kwargs:
            kwargs['stderr'] = subprocess.PIPE
    
    return original_popen(*args, **kwargs)


subprocess.Popen = popen_without_window



original_system = os.system

def system_without_window(command):
    if sys.platform == 'win32':
        process = subprocess.Popen(command, shell=True)
        process.wait()
        return process.returncode
    else:
        return original_system(command)


os.system = system_without_window

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
TIMEOUT = 3.0


current_time = datetime.now().strftime("%Y%m%d_%H%M%S")

# CSV path for pupil data
csv_out_path = os.path.join("C:\\Users\\dlabi\\OneDrive\\Desktop\\Palash_exp\\Duration_Estimation_Task\\Task\\data\\pupil_data\\", 
                           f"pupil_data_{current_time}.csv")

# CSV path for GSR data
gsr_csv_path = os.path.join("C:\\Users\\dlabi\\OneDrive\\Desktop\\Palash_exp\\Duration_Estimation_Task\\Task\\data\\gsr_data\\", 
                           f"gsr_data_{current_time}.csv")

# GSR data directory
gsr_data_dir = os.path.dirname(gsr_csv_path)
if not os.path.exists(gsr_data_dir):
    os.makedirs(gsr_data_dir)

# Experiment settings
num_trials_phase1 = 60
num_trials_phase2 = 2
press_interval_thresh = 0.75  # 750ms threshold for rapid pressing
ITI_duration = 2.0  # 2000ms inter-trial interval
ready_duration = 0.5  # 500ms ready text


GSR_SAMPLING_RATE = 1000  # 1000 Hz
GSR_SAMPLING_INTERVAL = 1.0 / GSR_SAMPLING_RATE  # 0.001 seconds between samples

# Image paths for positive and negative images
positive_images = ["P1_S.png", "P2_S.png", "P3_S.png"]
negative_images = ["N1_S.png", "N2_S.png", "N3_S.png"]

trial_time_limit = 20.0  # 25 seconds max trial duration

max_time_message_duration = 0.5  # 500ms max time message




# Set up participant info
info = {"Participant ID": ""}
dlg = gui.DlgFromDict(info)
if not dlg.OK:
    core.quit()

# Create data directory if it doesn't exist
if not os.path.exists('data'):
    os.makedirs('data')

# Data storage for experiment data
filename = f"C:\\Users\\dlabi\\OneDrive\\Desktop\\Palash_exp\\Duration_Estimation_Task\\Task\\data\\task_data\\data_{info['Participant ID']}.csv"
data_file = open(filename, "w")
data_file.write("phase,image_type,trial,image_name,trial_start,trial_end,reaction_time,response,viewing_duration,image_on_timestamps,image_off_timestamps\n")

# Open CSV file for pupil data
pupil_data_file = open(csv_out_path, "w", newline='')
pupil_writer = csv.writer(pupil_data_file)
pupil_writer.writerow(["timestamp", "confidence", "norm_pos_x", "norm_pos_y", "trial", "phase", "stimulus_state"])

# Initialize the GSR data
try:
    print("Looking for OpenSignals GSR stream...")
    gsr_streams = resolve_stream("name", "OpenSignals")
    if gsr_streams:
        gsr_inlet = StreamInlet(gsr_streams[0])
        gsr_connected = True
        logger.info("GSR stream found and connected")
        
        gsr_data_file = open(gsr_csv_path, "w", newline='')
        gsr_writer = csv.writer(gsr_data_file)
        gsr_writer.writerow(["timestamp", "gsr_value", "gsr_value_1", "gsr_value_2", "gsr_value_3","trial", "phase"])
    else:
        logger.warning("No GSR streams found")
        gsr_connected = False
except Exception as e:
    logger.error(f"Error connecting to GSR stream: {e}")
    gsr_connected = False

# Create a window of size 1920x1080 (black)
win = visual.Window([1920, 1080], color="black")

# Create LSL outlet
outlet_info = StreamInfo('PsychopyMarkers', 'Markers', 1, 0, 'string', 'psychopy001')

outlet = StreamOutlet(outlet_info)


# Define markers as strings
STIM_ON_MARKER = "Stim_On1"
STIM_OFF_MARKER = "Stim_Off2"
TRIAL_START_MARKER = "Trial_Start3"
TRIAL_END_MARKER = "Trial_End4"

# Start Lab Recorder via subprocess
lab_recorder_path = "C:\\Users\\dlabi\\Downloads\\Priyanshu\\Psychopy_exp\\VR_game\\Surge2022-20220609T083842Z-001\\GridPath\\Assets\\LabRecorder\\LabRecorderCLI.exe"

currentTime = "participant"  # Enter participant name here
subjectID = str(random.randint(1, 1000))

Dataset_path = "C:\\Users\\dlabi\\OneDrive\\Desktop\\Palash_exp\\Duration_Estimation_Task\\Task\\data\\eeg_data\\"  

Path(Dataset_path).mkdir(parents=True, exist_ok=True)

save_path = os.path.join(Dataset_path, f"{currentTime}{subjectID}.xdf")

# save xdf data
XDF_save_command = [lab_recorder_path, save_path, "'searchstr'"]

# Start the subprocess
XDF_Record = subprocess.Popen(XDF_save_command)

# Find and connect to pupil capture streams
logger.info("Looking for Pupil Capture streams...")
streams = pylsl.resolve_byprop("name", "pupil_capture", timeout=TIMEOUT)

if not streams:
    logger.error("No LSL streams of name 'pupil_capture' found")
    pupil_connected = False
else:
    logger.info("Connecting to {}".format(streams[0].hostname()))
    inlet = pylsl.StreamInlet(streams[0])
    inlet.open_stream(timeout=TIMEOUT)
    pupil_connected = True
    logger.info("Recording pupil data at {}".format(csv_out_path))

# Wait for LSL connection to establish
core.wait(2.0)

# Print confirmation on the screen
print("LSL Stream created with name:", outlet_info.name())
print("Outlet created successfully, ready to send markers")

def configure_ds8r_for_image(image_name):
    
    # Determine if image is positive or negative and then give electric shock based on demand value and pulse width
    is_positive = any(pos_img == image_name for pos_img in positive_images)
    image_type = "positive" if is_positive else "negative"

    demand_value = 80 if is_positive else 150
    pulse_width = 100 if is_positive else 250
    
    # Log the configuration
    print(f"Configuring DS8R for {image_type} image: {image_name}")
    print(f"Setting demand value to: {demand_value}")
    
    return DS8R(
        demand=demand_value,  # Variable demand based on image type
        pulse_width=pulse_width,      # Keep original value
        enabled=1,            # Keep original value
        dwell=10,            # Keep original value
        mode=1,              # Keep original value
        polarity=1,          # Keep original value
        source=1,            # Keep original value
        recovery=20          # Keep original value
    )

def run_ds8r_silently(image_name):
    try:
        ctl = configure_ds8r_for_image(image_name)
        print(f"Running DS8R for image: {image_name}")
        
        if hasattr(ctl, '_cmd') and isinstance(ctl._cmd, str):
            subprocess.run(ctl._cmd, shell=True, check=True)
        else:
            ctl.run()
            
    except Exception as e:
        pass



# Instructions
instructions = visual.TextStim(win, text="Trial Phase :\nRapidly press the UP ARROW key to view the image.\nThe image will remain visible as long as you keep pressing.\nIf you stop pressing, the image will disappear and the next trial will begin.\n\nPress SPACE to begin.", color="white")
instructions.draw()
win.flip()
event.waitKeys(keyList=["space"])

# Create ready text stimulus
ready_text = visual.TextStim(win, text="Ready", color="white", height=0.1)

max_time_message = visual.TextStim(win, text="Max time limit reached", color="red", height=0.1)


# Global experiment clock
global_clock = core.Clock()



# Function to collect GSR data
def collect_gsr_data(trial, phase):
    if gsr_connected:
        try:
            # Pull the newest sample without blocking
            sample, timestamp = gsr_inlet.pull_sample(timeout=0.0)
            if sample is not None:
                # Write to CSV file, assuming sample[1] is the GSR value
                gsr_writer.writerow([timestamp, sample[1],sample[2],sample[3],sample[4], trial, phase])
                return True
        except Exception as e:
            logger.warning(f"Error collecting GSR data: {e}")
    return False




#image_type = ["positive", "negative"]

# Trial Phase

trial_positive_trials = positive_images * 1
trial_negative_trials = negative_images * 1
trial_all_trials = trial_positive_trials + trial_negative_trials
random.shuffle(trial_all_trials)  # Shuffle to randomize order

#image_type = [positive_images_str,negative_images_str]


for trial , image_name in enumerate(trial_all_trials,start=1):
    outlet.push_sample([TRIAL_START_MARKER])
    print(f"Test Phase - Trial {trial} started - marker sent")
    
   
    
    # Show ready text
    ready_text.draw()
    win.flip()
    core.wait(ready_duration)
    
    stimulus = visual.ImageStim(win, image=image_name, size=(650, 520),units="pix")
    
    #stimulus = visual.ImageStim(win, image=image_name)
    blank = visual.TextStim(win, text="", color="white")  # Blank screen when key not pressed

    # Trial setup
    trial_clock = core.Clock()
    response = "no_response"
    response_time = None
    viewing_duration = 0
    image_on_timestamps = []
    image_off_timestamps = []
    
    # Start the trial
    trial_start = global_clock.getTime()
    start_time = trial_clock.getTime()
    last_press_time = 0
    show_image = False
    was_showing_image = False
    trial_active = True
    
    # Start collecting pupil and GSR data for this trial
    last_pupil_pull_time = 0
    last_gsr_pull_time = 0
    
    # Track current stimulus state for pupil and GSR data
    stimulus_state = "OFF"
    
    # To track key presses between frames
    pressed_keys = []
    
    
    event.clearEvents()
    
    # Continue until participant stops pressing
    while trial_active:
        current_time = trial_clock.getTime()
        
        # Collect pupil data (every 10ms)
        if pupil_connected and (time.time() - last_pupil_pull_time) > 0.01:
            last_pupil_pull_time = time.time()
            # Pull data from the inlet
            samples, timestamps = inlet.pull_chunk(timeout=0.0)
            if samples:
                for sample, timestamp in zip(samples, timestamps):
                    # confidence, norm_pos_x, norm_pos_y, diameter, trial, phase, stimulus_state
                    if len(sample) >= 4:  # Ensure sample has enough data
                        pupil_writer.writerow([
                            timestamp, 
                            sample[0], 
                            sample[1], 
                            sample[2], 
                            trial, 
                            "Trial phase", 
                            stimulus_state
                        ])
        
        
        if gsr_connected and (time.time() - last_gsr_pull_time) > GSR_SAMPLING_INTERVAL:
            last_gsr_pull_time = time.time()
            collect_gsr_data(trial, "Trial phase")
        

        pressed_keys = event.getKeys(keyList=["up", "escape"], timeStamped=trial_clock)
        
        # Process each key press individually
        if pressed_keys:
            for key, press_time in pressed_keys:
                if key == "escape":
                    # Close everything and quit
                    data_file.close()
                    pupil_data_file.close()
                    if gsr_connected:
                        gsr_data_file.close()
                    try:
                        XDF_Record.terminate()
                        print("Lab Recorder terminated")
                    except:
                        pass
                    win.close()
                    core.quit()
                    
                if key == "up":
                    # Record first press time for data
                    if response == "no_response":
                        response = "pressed"
                        response_time = press_time - start_time
                    
                    # Update last press time and show image
                    last_press_time = press_time
                    show_image = True
                    
                    # Run DS8R control for EACH button press to stimulate electric shock
                    print(f"Trial Phase - Running ctl.run() at {press_time}")
                    
                    
                    run_ds8r_silently(image_name)
                    
                  
        
        # Check if we should still be showing the image based on last press time
        if current_time - last_press_time > press_interval_thresh:
            show_image = False
            
            # If they were previously showing the image but stopped pressing,
            # end the trial
            if response == "pressed" and was_showing_image:
                trial_active = False
                viewing_duration = last_press_time - (start_time + response_time)
                
        if current_time >= trial_time_limit:
            trial_active = False
                
                # Save current viewing state before showing message
            if was_showing_image:
                image_off_timestamps.append(global_clock.getTime())
                was_showing_image = False
            
            # Show max time message
            max_time_message.draw()
            win.flip()
            core.wait(max_time_message_duration)
            
            # Calculate viewing duration from timestamps
            if image_on_timestamps and image_off_timestamps:
                viewing_duration = sum([off - on for on, off in zip(image_on_timestamps, image_off_timestamps)])
            
            # Don't continue with the rest of the loop
            break
        
        
        # Track image on/off transitions and send markers
        if show_image and not was_showing_image:
            outlet.push_sample([STIM_ON_MARKER])
            print("Image ON - marker sent")
            image_on_timestamps.append(global_clock.getTime())
            was_showing_image = True
            stimulus_state = "ON"  # Update stimulus state for pupil and GSR data
        elif not show_image and was_showing_image:
            outlet.push_sample([STIM_OFF_MARKER])
            print("Image OFF - marker sent")
            image_off_timestamps.append(global_clock.getTime())
            was_showing_image = False
            stimulus_state = "OFF"  # Update stimulus state for pupil and GSR data
            
        # Display appropriate stimulus
        if show_image:
            stimulus.draw()
        else:
            blank.draw()
            
        win.flip()

    # Ensure we have a final image_off timestamp if needed
    if was_showing_image:
        image_off_timestamps.append(global_clock.getTime())
        stimulus_state = "OFF"
    
    # Record trial end time
    trial_end = global_clock.getTime()
    
    # Calculate final viewing duration if not already done
    if viewing_duration == 0 and image_on_timestamps and image_off_timestamps:
        viewing_duration = sum([off - on for on, off in zip(image_on_timestamps, image_off_timestamps)])
    
    # send trial end marker
    outlet.push_sample([TRIAL_END_MARKER])
    print(f"Trial {trial} ended - marker sent")
    
    # Convert timestamp lists to strings to save inside csv file
    image_on_str = ";".join([str(t) for t in image_on_timestamps])
    image_off_str = ";".join([str(t) for t in image_off_timestamps])

    # Log data for Phase 1 and save inside csv
    data_file.write(f"Trial Phase,image_type,{trial},{image_name},{trial_start},{trial_end},{response_time},{response},{viewing_duration},{image_on_str},{image_off_str}\n")

    # Inter-trial interval
    blank.draw()
    win.flip()
    core.wait(ITI_duration)





# 30-second break
break_message = visual.TextStim(win, text="Take a short 30-second break.\n\nPhase 1 will begin shortly.", color="white")
break_message.draw()
win.flip()
core.wait(30.0)


# Instructions
instructions = visual.TextStim(win, text="Phase 1:\nRapidly press the UP ARROW key to view the image.\nThe image will remain visible as long as you keep pressing.\nIf you stop pressing, the image will disappear and the next trial will begin.\n\nPress SPACE to begin.", color="white")
instructions.draw()
win.flip()
event.waitKeys(keyList=["space"])


# Create a randomized list of images (each image appears 5 times) => 30 trials
positive_trials = positive_images * 5
negative_trials = negative_images * 5
all_trials = positive_trials + negative_trials
random.shuffle(all_trials)  # Shuffle to randomize order

# Phase 1
for trial , image_name in enumerate(all_trials,start=7):
    outlet.push_sample([TRIAL_START_MARKER])
    print(f"Phase 1 - Trial {trial} started - marker sent")
    
   
    
    # Show ready text
    ready_text.draw()
    win.flip()
    core.wait(ready_duration)
    
    stimulus = visual.ImageStim(win, image=image_name, size=(650, 520),units="pix")
    
    #stimulus = visual.ImageStim(win, image=image_name)
    blank = visual.TextStim(win, text="", color="white")  # Blank screen when key not pressed

    # Trial setup
    trial_clock = core.Clock()
    response = "no_response"
    response_time = None
    viewing_duration = 0
    image_on_timestamps = []
    image_off_timestamps = []
    
    # Start the trial
    trial_start = global_clock.getTime()
    start_time = trial_clock.getTime()
    last_press_time = 0
    show_image = False
    was_showing_image = False
    trial_active = True
    
    # Start collecting pupil and GSR data for this trial
    last_pupil_pull_time = 0
    last_gsr_pull_time = 0
    
    # Track current stimulus state for pupil and GSR data
    stimulus_state = "OFF"
    
    # To track key presses between frames
    pressed_keys = []
    
    event.clearEvents()
    
    # Continue until participant stops pressing
    while trial_active:
        current_time = trial_clock.getTime()
        
        # Collect pupil data (every 10ms)
        if pupil_connected and (time.time() - last_pupil_pull_time) > 0.01:
            last_pupil_pull_time = time.time()
            # Pull data from the inlet
            samples, timestamps = inlet.pull_chunk(timeout=0.0)
            if samples:
                for sample, timestamp in zip(samples, timestamps):
                    # confidence, norm_pos_x, norm_pos_y, diameter, trial, phase, stimulus_state
                    if len(sample) >= 4:  # Ensure sample has enough data
                        pupil_writer.writerow([
                            timestamp, 
                            sample[0], 
                            sample[1], 
                            sample[2], 
                            trial, 
                            "phase1", 
                            stimulus_state
                        ])
        
        # Collect GSR data at 1000Hz
        if gsr_connected and (time.time() - last_gsr_pull_time) > GSR_SAMPLING_INTERVAL:
            last_gsr_pull_time = time.time()
            collect_gsr_data(trial, "phase1")
        
        pressed_keys = event.getKeys(keyList=["up", "escape"], timeStamped=trial_clock)
        
        # Process each key press individually
        if pressed_keys:
            for key, press_time in pressed_keys:
                if key == "escape":
                    # Close everything and quit
                    data_file.close()
                    pupil_data_file.close()
                    if gsr_connected:
                        gsr_data_file.close()
                    try:
                        XDF_Record.terminate()
                        print("Lab Recorder terminated")
                    except:
                        pass
                    win.close()
                    core.quit()
                    
                if key == "up":
                    # Record first press time for data
                    if response == "no_response":
                        response = "pressed"
                        response_time = press_time - start_time
                    
                    # Update last press time and show image
                    last_press_time = press_time
                    show_image = True
                    
                    run_ds8r_silently(image_name)
                    
        
        # Check if we should still be showing the image based on last press time
        if current_time - last_press_time > press_interval_thresh:
            show_image = False
            
            # If they were previously showing the image but stopped pressing,
            # end the trial
            if response == "pressed" and was_showing_image:
                trial_active = False
                viewing_duration = last_press_time - (start_time + response_time)
                
        if current_time >= trial_time_limit:
            trial_active = False
                
                # Save current viewing state before showing message
            if was_showing_image:
                image_off_timestamps.append(global_clock.getTime())
                was_showing_image = False
            
            # Show max time message
            max_time_message.draw()
            win.flip()
            core.wait(max_time_message_duration)
            
            # Calculate viewing duration from timestamps
            if image_on_timestamps and image_off_timestamps:
                viewing_duration = sum([off - on for on, off in zip(image_on_timestamps, image_off_timestamps)])
            
            # Don't continue with the rest of the loop
            break
        
        
        # Track image on/off transitions and send markers
        if show_image and not was_showing_image:
            outlet.push_sample([STIM_ON_MARKER])
            print("Image ON - marker sent")
            image_on_timestamps.append(global_clock.getTime())
            was_showing_image = True
            stimulus_state = "ON"  # Update stimulus state for pupil and GSR data
        elif not show_image and was_showing_image:
            outlet.push_sample([STIM_OFF_MARKER])
            print("Image OFF - marker sent")
            image_off_timestamps.append(global_clock.getTime())
            was_showing_image = False
            stimulus_state = "OFF"  # Update stimulus state for pupil and GSR data
            
        # Display appropriate stimulus
        if show_image:
            stimulus.draw()
        else:
            blank.draw()
            
        win.flip()

    # Ensure we have a final image_off timestamp if needed
    if was_showing_image:
        image_off_timestamps.append(global_clock.getTime())
        stimulus_state = "OFF"
    
    # Record trial end time
    trial_end = global_clock.getTime()
    
    # Calculate final viewing duration if not already done
    if viewing_duration == 0 and image_on_timestamps and image_off_timestamps:
        viewing_duration = sum([off - on for on, off in zip(image_on_timestamps, image_off_timestamps)])
    
    # send trial end marker
    outlet.push_sample([TRIAL_END_MARKER])
    print(f"Trial {trial} ended - marker sent")
    
    # Convert timestamp lists to strings to save inside csv file
    image_on_str = ";".join([str(t) for t in image_on_timestamps])
    image_off_str = ";".join([str(t) for t in image_off_timestamps])

    # Log data for Phase 1
    data_file.write(f"phase1,image_type,{trial},{image_name},{trial_start},{trial_end},{response_time},{response},{viewing_duration},{image_on_str},{image_off_str}\n")

    # Inter-trial interval
    blank.draw()
    win.flip()
    core.wait(ITI_duration)

# 30-second break
break_message = visual.TextStim(win, text="Take a short 2 minutes break.\n\nPhase 2 will begin shortly.", color="white")
break_message.draw()
win.flip()
core.wait(120.0)

# Instructions for Phase 2
instructions = visual.TextStim(win, text="Phase 2:\nRapidly press the UP ARROW key to view the image.\nThe image will remain visible as long as you keep pressing.\nIf you stop pressing, the image will disappear and the next trial will begin.\n\nPress SPACE to begin.", color="white")
instructions.draw()
win.flip()
event.waitKeys(keyList=["space"])

positive_trials = positive_images * 5
negative_trials = negative_images * 5
all_trials = positive_trials + negative_trials
random.shuffle(all_trials)  # Shuffle to randomize order

# Phase 2
for trial,image_name in enumerate(all_trials,start=37):
    outlet.push_sample([TRIAL_START_MARKER])
    print(f"Phase 2 - Trial {trial} started - marker sent")
    
    
    # Show ready text
    ready_text.draw()
    win.flip()
    core.wait(ready_duration)
    
    stimulus = visual.ImageStim(win, image=image_name, size=(650, 520),units="pix")
    
    #stimulus = visual.ImageStim(win, image=image_name)
    blank = visual.TextStim(win, text="", color="white")

    # Trial setup
    trial_clock = core.Clock()
    response = "no_response"
    response_time = None
    viewing_duration = 0
    image_on_timestamps = []
    image_off_timestamps = []
    
    # Start the trial
    trial_start = global_clock.getTime()
    start_time = trial_clock.getTime()
    last_press_time = 0
    show_image = False
    was_showing_image = False
    trial_active = True
    
    # Start collecting pupil and GSR data for this trial
    last_pupil_pull_time = 0
    last_gsr_pull_time = 0
    
    # Track current stimulus state for pupil and GSR data
    stimulus_state = "OFF"
    
    # To track key presses between frames
    pressed_keys = []
    
    event.clearEvents()
    
    while trial_active:
        current_time = trial_clock.getTime()
        
        # Collect pupil data (every 10ms)
        if pupil_connected and (time.time() - last_pupil_pull_time) > 0.01:
            last_pupil_pull_time = time.time()
            # Pull data from the inlet
            samples, timestamps = inlet.pull_chunk(timeout=0.0)
            if samples:
                for sample, timestamp in zip(samples, timestamps):
                    # confidence, norm_pos_x, norm_pos_y, diameter, trial, phase, stimulus_state, image_type, image_name
                    if len(sample) >= 4:  # Ensure sample has enough data
                        pupil_writer.writerow([
                            timestamp, 
                            sample[0], 
                            sample[1], 
                            sample[2], 
                            trial, 
                            "phase2", 
                            stimulus_state
                        ])
        
        # Collect GSR data at 1000Hz
        if gsr_connected and (time.time() - last_gsr_pull_time) > GSR_SAMPLING_INTERVAL:
            last_gsr_pull_time = time.time()
            collect_gsr_data(trial, "phase2")
        
        # Get all key presses for this frame
        pressed_keys = event.getKeys(keyList=["up", "escape"], timeStamped=trial_clock)
        
        # Process each key press individually
        if pressed_keys:
            for key, press_time in pressed_keys:
                if key == "escape":
                    data_file.close()
                    pupil_data_file.close()
                    if gsr_connected:
                        gsr_data_file.close()
                    try:
                        XDF_Record.terminate()
                        print("Lab Recorder terminated")
                    except:
                        pass
                    win.close()
                    core.quit()
                    
                if key == "up":
                    if response == "no_response":
                        response = "pressed"
                        response_time = press_time - start_time
                    
                    last_press_time = press_time
                    show_image = True
                    
                    run_ds8r_silently(image_name)
                    
        
        if current_time - last_press_time > press_interval_thresh:
            show_image = False
            
            if response == "pressed" and was_showing_image:
                trial_active = False
                viewing_duration = last_press_time - (start_time + response_time)
                
        if current_time >= trial_time_limit:
            trial_active = False
                
                # Save current viewing state before showing message
            if was_showing_image:
                image_off_timestamps.append(global_clock.getTime())
                was_showing_image = False
            
            # Show max time message
            max_time_message.draw()
            win.flip()
            core.wait(max_time_message_duration)
            
            # Calculate viewing duration from timestamps
            if image_on_timestamps and image_off_timestamps:
                viewing_duration = sum([off - on for on, off in zip(image_on_timestamps, image_off_timestamps)])
            
            # Don't continue with the rest of the loop
            break
        
        
        if show_image and not was_showing_image:
            outlet.push_sample([STIM_ON_MARKER])
            print("P2 - Image ON - marker sent")
            image_on_timestamps.append(global_clock.getTime())
            was_showing_image = True
            stimulus_state = "ON"  # Update stimulus state for pupil and GSR data
        elif not show_image and was_showing_image:
            outlet.push_sample([STIM_OFF_MARKER])
            print("P2 - Image OFF - marker sent")
            image_off_timestamps.append(global_clock.getTime())
            was_showing_image = False
            stimulus_state = "OFF"  # Update stimulus state for pupil and GSR data
            
        if show_image:
            stimulus.draw()
        else:
            blank.draw()
            
        win.flip()

    if was_showing_image:
        image_off_timestamps.append(global_clock.getTime())
        stimulus_state = "OFF"
    
    trial_end = global_clock.getTime()
    
    # Calculate final viewing duration if not already done
    if viewing_duration == 0 and image_on_timestamps and image_off_timestamps:
        viewing_duration = sum([off - on for on, off in zip(image_on_timestamps, image_off_timestamps)])
    
    outlet.push_sample([TRIAL_END_MARKER])
    print(f"Phase 2 - Trial {trial} ended - marker sent")

    data_file.write(f"phase2,image_type,{trial},{image_name},{trial_start},{trial_end},{response_time},{response},{viewing_duration},{image_on_str},{image_off_str}\n")

    blank.draw()
    win.flip()
    core.wait(ITI_duration)

# Final marker
outlet.push_sample(["Experiment_End"])
print("Experiment ended - final marker sent")

# End message
end_message = visual.TextStim(win, text="Thank you for participating!", color="white")
end_message.draw()
win.flip()
core.wait(2.0)

# Cleanup
data_file.close()
pupil_data_file.close()
if gsr_connected:
    gsr_data_file.close()

# Terminate Lab Recorder process
try:
    XDF_Record.terminate()
    print("Lab Recorder terminated")
except:
    print("Could not terminate Lab Recorder")

win.close()

# Kill the recorder if necessary
XDF_Record.kill()
core.quit()