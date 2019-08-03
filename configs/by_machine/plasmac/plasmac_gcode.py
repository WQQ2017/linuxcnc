#! /usr/bin/python

'''
plasmac_gcode.py

Copyright (C) 2019  Phillip A Carter

This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc
51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
'''

import os
import sys
import linuxcnc
import math
 
ini = linuxcnc.ini(os.environ['INI_FILE_NAME'])

codeError = False
cutoffEnable = False
holeActive = False
holeEnable = False
imperial = [25.4, 6]
lastX = 0
lastY = 0
infile = sys.argv[1]
materialFile = ini.find('EMC', 'MACHINE').lower() + '_material.cfg'
metric = [1, 4]
minDiameter = 32
scale, precision = imperial if ini.find('TRAJ', 'LINEAR_UNITS').lower() == 'inch' else metric
torchEnable = True
velocity = 60

# check if arc is a hole
def check_if_hole():
    global lastX, lastY
    endX = lastX
    endY = lastY
    if 'x' in line: endX = get_position('x')
    if 'y' in line: endY = get_position('y')
    if lastX == endX and lastY == endY:
        I = J = 0
        if 'i' in line: I = get_position('i')
        if 'j' in line: J = get_position('j')
        radius = get_hole_radius(I, J)
        print(line)
        if cutoffEnable:
            negative_cutoff(I, J, radius)
    else:
        print(line)
        lastX = endX
        lastY = endY

# turn torch off and move 4mm (0.157) past hole end
def negative_cutoff(I, J, radius):
    global lastX, lastY, torchEnable
    centerX = lastX + I
    centerY = lastY + J
    cosA = math.cos(4 / radius / scale)
    sinA = math.sin(4 / radius / scale)
    cosB = ((lastX - centerX) / radius)
    sinB = ((lastY - centerY) / radius)
    print('m62p3 (disable torch)')
    torchEnable = False
    #clockwise arc
    if line.startswith('g2'):
        endX = centerX + radius * ((cosB * cosA) + (sinB * sinA))
        endY = centerY + radius * ((sinB * cosA) - (cosB * sinA))
        dir = '2'
    #counterclockwise arc
    else:
        endX = centerX + radius * ((cosB * cosA) - (sinB * sinA))
        endY = centerY + radius * ((sinB * cosA) + (cosB * sinA))
        dir = '3'
    print('g{0}x{1:0.{5}f}y{2:0.{5}f}i{3:0.{5}f}j{4:0.{5}f}'.format(dir, endX, endY, I, J, precision))
    lastX = endX
    lastY = endY

# get hole radius and set velocity percentage
def get_hole_radius(I, J):
    global holeActive
    radius = math.sqrt((I ** 2) + (J ** 2))
    # velocity reduction required
    if radius < (minDiameter / 2 / scale):
        print('m67e3q{0} (radius: {1:0.3f}, velocity: {0}%)'.format(velocity, radius))
        holeActive = True
    # no velocity reduction required
    else:
        if holeActive:
            print('m67e3q0 (arc complete, velocity 100%)')
            holeActive = False
    return radius

# get axis position
def get_position(axis):
    tmp1 = line.split(axis)[1]
    if not tmp1[0].isdigit() and not tmp1[0] == '.' and not tmp1[0] == '-':
        tmp1 = tmp1[1:]
    tmp2 = ''
    while 1:
        if tmp1[0].isdigit() or tmp1[0] == '.' or tmp1[0] == '-':
            tmp2 += tmp1[0]
        if len(tmp1) > 1:
            tmp1 = tmp1[1:]
        else:
            break
    return float(tmp2)

# get the last X and Y positions
def get_last_position(Xpos, Ypos):
    if line.startswith('g') or \
       line.startswith('x') or \
       line.startswith('y'):
        if 'x' in line:
            Xpos = get_position('x')
        if 'y' in line:
            Ypos = get_position('y')
    return Xpos, Ypos

# comment out all Z commands
def comment_out_z_commands():
    global holeActive
    newline = ''
    newz = ''
    removing = 0
    comment = 0
    for bit in line:
        if comment:
            if bit == ')':
                comment = 0
            newline += bit
        elif removing:
            if bit in '0123456789.- ':
                newz += bit
            else:
                removing = 0
                if newz:
                    newz = newz.rstrip() + ')'
                newline += bit
        elif bit == '(':
            comment = 1
            newline += bit
        elif bit == 'z':
            removing = 1
            newz += '(' + bit
        else:
            newline += bit
    if holeActive:
        print 'm67e3q0 (arc complete, velocity 100%)'
        holeActive = False
    print('{} {}'.format(newline, newz))

# check if math used or explicit values
def check_math(axis):
    global codeError
    tmp1 = line.split(axis)[1]
    if tmp1.startswith('[') or tmp1.startswith('#'):
        codeError = True
        print('*** PlasmaC GCode parser\n'
              '*** requires explicit values\n'
              'Error in line #{}: {}'
              '*** disable hole sensing\n'
              '*** or edit GCode to suit\n'
              .format(count, line))

# get a list of known materials
with open(materialFile, 'r') as f_in:
    materialList = [0]
    for line in f_in:
        if not line.startswith('#'):
            if line.startswith('[MATERIAL_NUMBER_') and line.strip().endswith(']'):
                a,b,c = line.split('_')
                t_number = int(c.replace(']',''))
                materialList.append(t_number)
f = open(infile, 'r')
 
# first pass, check for valid material numbers and distance modes
count = 0
for line in f:
    count += 1
    # convert to lower case and remove spaces
    line = line.strip().lower().replace(' ','')
    # if line is a comment
    if line.startswith(';') or line.startswith('('):
        continue
    # if material change
    if 'm190' in line:
        first, last = line.lower().strip().split('p',1)
        material = ''
        # get the material number
        for mNumber in last.strip():
            if mNumber in '0123456789':
                material += mNumber
        # if invalid material number
        if int(material) not in materialList:
            codeError = True
            print('*** The following materials are missing from:\n'
                  '*** {}\n'
                  '*** Material #{}\n'
                  'Error in line #{}: {}\n'
                  .format(materialFile, material, count, line))
    # set units
    if 'g21' in line:
        scale, precision = metric
    elif 'g20' in line:
        scale, precision = imperial
    # if hole sensing code
    if line.startswith('#<holes>'):
        if line.split('=')[1][0] == '1':
            holeEnable = True
        elif line.split('=')[1][0] == '2':
            holeEnable = cutoffEnable = True
        else:
            holeEnable = cutoffEnable = False
    # if hole sensing enabled
    if holeEnable:
        # if unsupported distance mode
        if 'g91' in line and not 'g91.1' in line:
            codeError = True
            print('*** PlasmaC GCode parser only\n'
                  '*** supports Distance Mode G90\n'
                  'Error in line #{}: {}\n'
                  .format(count, line))
        # if unsupported arc distance mode
        if 'g90.1' in line:
            codeError = True
            print('*** PlasmaC GCode parser only\n'
                  '*** supports Arc Distance Mode G91.1\n'
                  'Error in line #{}: {}\n'
                  .format(count, line))
        if 'x' in line: check_math('x')
        if 'y' in line: check_math('y')
        if 'i' in line: check_math('i')
        if 'j' in line: check_math('j')
        if '_diameter>' in line:
            if not line.startswith('#<m_d') and not line.startswith('#<i_d'):
                codeError = True
                print('*** invalid diameter word\n'
                      'Error in line #{}: {}\n'
                      .format(count, line))

# second, pass process every line
if not codeError:
    f = open(infile, 'r')
    for line in f:
        # convert to lower case and remove spaces
        line = line.strip().lower().replace(' ','')
        # remove line numbers
        if line.startswith('n'):
            line = line.split('n',1)[-1]
            while line[0].isdigit() or line[0] == '.':
                line = line[1:]
        # remove leading 0's from G & M codes
        if line.startswith('g') or line.startswith('m'):
            while line[1] == '0':
                if line[2].isdigit():
                    line = line[:1] + line[2:]
                else:
                    break
        # if a commented line then print it
        if line.startswith(';') or line.startswith('('):
            print line
        # if segment is a G2 or G3 arc
        elif line.startswith('#<holes>'):
            if line.split('=')[1][0] == '1':
                holeEnable = True
                print('{} (velocity reduction for holes)'.format('#<holes>=1'))
            elif line.split('=')[1][0] == '2':
                holeEnable = cutoffEnable = True
                print('{} (overcut for holes)'.format('#<holes>=2'))
            else:
                holeEnable = cutoffEnable = False
                print(line)
        elif '_diameter>' in line:
            if line.startswith('#<i_d'):
                multiplier = 25.4
            else:
                multiplier = 1
            line = line.split('=')[1]
            if '(' in line or ';':
                line = line.replace('(',';').split(';')[0]
            print('(LINE: {})'.format(line))
            minDiameter = float(line) * multiplier
            print('(DIA: {})'.format(minDiameter))
        elif (line.startswith('g2') or line.startswith('g3')) and line[2].isalpha():
            if holeEnable:
                check_if_hole()
            else:
                print(line)
        # if torch off, flag it then print it
        elif line.startswith('m62p3') or line.startswith('m64p3'):
            torchEnable = False
            print(line)
        # if torch on, flag it then print it
        elif line.startswith('m63p3') or line.startswith('m65p3'):
            torchEnable = True
            print(line)
        # if spindle off
        elif line.startswith('m5'):
            print(line)
            # restore velocity if required
            if holeActive:
                print('m68e3q0 (arc complete, velocity 100%)')
                holeActive = False
            # if torch off, allow torch on 
            if not torchEnable:
                print('m65p3 (enable torch)')
                torchEnable = True
        # if program end
        elif 'm2' in line or 'm30' in line or '%' in line:
            # restore hole sensing to default
            if holeEnable:
                print('#<holes> = 0 (disable hole sensing)')
                holeEnable = False
            # restore velocity if required
            if holeActive:
                print('m68e3q0 (arc complete, velocity 100%)')
                holeActive = False
            # if torch off, allow torch on 
            if not torchEnable:
                print('m65p3 (enable torch)')
                torchEnable = True
            print(line)
        # if no Z axis in line
        elif not 'z' in line:
            if holeEnable:
                # restore velocity if required
                if holeActive:
                    print('m67e3q0 (arc complete, velocity 100%)')
                    holeActive = False
                lastX, lastY = get_last_position(lastX, lastY)
            print(line)
        # if only Z axis in line then comment it out
        elif 1 not in [c in line for c in 'xyabcuvw']:
            #print('Z only')
            print('({})'.format(line))
        # mixed axes in line, comment out the Z axis
        else:
            if holeEnable:
                lastX, lastY = get_last_position(lastX, lastY)
            comment_out_z_commands()