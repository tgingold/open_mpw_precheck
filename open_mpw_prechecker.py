# Copyright 2020 Efabless Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os.path
import argparse
import subprocess
from utils.utils import *
import base_checks.check_yaml as check_yaml
import base_checks.check_license as check_license
import drc_checks.gds_drc_checker as gds_drc_checker
import consistency_checks.consistency_checker as consistency_checker

default_logger_path = '/usr/local/bin/full_log.log'


def parse_netlists(target_path, top_level_netlist, user_level_netlist, lc=logging_controller(default_logger_path)):
    verilog_netlist = []
    spice_netlist = []
    toplvl_extension = os.path.splitext(top_level_netlist)[1]
    userlvl_extension = os.path.splitext(user_level_netlist)[1]
    if str(toplvl_extension) == '.v' and str(userlvl_extension) == '.v':
        verilog_netlist = [str(target_path) + '/' + str(top_level_netlist), str(target_path) + '/' + str(user_level_netlist)]
    elif str(toplvl_extension) == '.spice' and str(userlvl_extension) == '.spice':
        spice_netlist = [str(target_path) + '/' + str(top_level_netlist), str(target_path) + '/' + str(user_level_netlist)]
    else:
        lc.print_control(
            "{{FAIL}} the provided top level and user level netlists are neither a .spice or a .v files. Please adhere to the required input type.")
        lc.exit_control(2)
    return verilog_netlist, spice_netlist


def run_check_sequence(target_path, output_directory=None, waive_fuzzy_checks=False, skip_drc=False, drc_only=False):
    if output_directory is None:
        output_directory = str(target_path) + '/checks'
    # Create the logging controller
    lc = logging_controller(str(output_directory) + '/full_log.log')
    lc.create_full_log()

    steps = 4
    if drc_only:
        steps = 1
    stp_cnt = 0

    lc.print_control("Executing Step " + str(stp_cnt) + " of " + str(steps) + ": Uncompressing the gds files")
    # Decompress project items and copies all GDS-II files to top level.
    run_prep_cmd = "cd {target_path}; make uncompress;".format(
        target_path=target_path
    )

    process = subprocess.Popen(run_prep_cmd, stdout=subprocess.PIPE, shell=True)
    process.communicate()[0].strip()
    lc.print_control("Step " + str(stp_cnt) + " done without fatal errors.")
    stp_cnt += 1

    if drc_only == False:
        # NOTE: Step 1: Check LICENSE.
        lc.print_control("{{PROGRESS}} Executing Step " + str(stp_cnt) + " of " + str(steps) + ": Checking License files.")
        if check_license.check_main_license(target_path):
            lc.print_control("{{PROGRESS}} APACHE-2.0 LICENSE exists in target path")
        else:
            lc.print_control("{{FAIL}} APACHE-2.0 LICENSE is Not Found in target path\nTEST FAILED AT STEP " + str(stp_cnt))
            lc.exit_control(2)

        third_party_licenses = check_license.check_lib_license(target_path + '/third-party/')

        if len(third_party_licenses):
            for key in third_party_licenses:
                if third_party_licenses[key] == False:
                    lc.print_control("{{FAIL}} Third Party" + str(key) + "License Not Found\nTEST FAILED AT STEP " + str(stp_cnt))
                    lc.exit_control(2)
            lc.print_control("{{PROGRESS}} Third Party Licenses Found.\nStep " + str(stp_cnt) + " done without fatal errors.")
        else:
            lc.print_control("{{PROGRESS}} No third party libraries found.\nStep " + str(stp_cnt) + " done without fatal errors.")

        spdx_non_compliant_list = check_license.check_dir_spdx_compliance([], target_path)
        if spdx_non_compliant_list:
            lc.print_control(
                "{{SPDX COMPLIANCE WARNING}} We found %s files not compliant with the SPDX Standard \n%s" % (spdx_non_compliant_list.__len__(),
                                                                                                             spdx_non_compliant_list[:20]))
        else:
            lc.print_control("{{SPDX COMPLIANCE PASSED}} Project is compliant with SPDX Standard")

        stp_cnt += 1

        # NOTE: Step 2: Check YAML description.
        lc.print_control("{{PROGRESS}} Executing Step " + str(stp_cnt) + " of " + str(steps) + ": Checking YAML description.")
        check, top_level_netlist, user_level_netlist = check_yaml.check_yaml(target_path)
        if check:
            lc.print_control("{{PROGRESS}} YAML file valid!\nStep " + str(stp_cnt) + " done without fatal errors.")
        else:
            lc.print_control(
                "{{FAIL}} YAML file not valid in target path, please check the README.md for more info on the structure\nTEST FAILED AT STEP " + str(
                    stp_cnt))
            lc.exit_control(2)
        stp_cnt += 1

        verilog_netlist, spice_netlist = parse_netlists(target_path, top_level_netlist, user_level_netlist, lc)

        # NOTE: Step 3: Check Fuzzy Consistency.
        lc.print_control("{{PROGRESS}} Executing Step " + str(stp_cnt) + " of " + str(steps) + ": Executing Fuzzy Consistency Checks.")
        check, reason = consistency_checker.fuzzyCheck(target_path=target_path, spice_netlist=spice_netlist, verilog_netlist=verilog_netlist,
                                                       output_directory=output_directory, waive_consistency_checks=waive_fuzzy_checks, lc=lc)
        if check:
            lc.print_control("{{PROGRESS}} Fuzzy Consistency Checks Passed!\nStep " + str(stp_cnt) + " done without fatal errors.")
        else:
            lc.print_control("{{FAIL}} Consistency Checks Failed+ Reason: " + reason + "\nTEST FAILED AT STEP " + str(stp_cnt))
            lc.exit_control(2)
        stp_cnt += 1

        # NOTE: Step 4: Not Yet Implemented.

    # NOTE: Step 5: Perform DRC checks on the GDS.
    # assumption that we'll always be using a caravel top module based on what's on step 3
    lc.print_control("{{PROGRESS}} Executing Step " + str(stp_cnt) + " of " + str(steps) + ": Checking DRC Violations.")
    if skip_drc:
        lc.print_control("{{WARNING}} Skipping DRC Checks...")
    else:
        check, reason = gds_drc_checker.gds_drc_check(str(target_path) + '/gds/', 'caravel', output_directory, lc)

        if check:
            lc.print_control("{{PROGRESS}} DRC Checks on GDS-II Passed!\nStep " + str(stp_cnt) + " done without fatal errors.")
        else:
            lc.print_control("{{FAIL}} DRC Checks on GDS-II Failed, Reason: " + reason + "\nTEST FAILED AT STEP " + str(stp_cnt))
            lc.exit_control(2)
    stp_cnt += 1

    # NOTE: Step 6: Not Yet Implemented.
    # NOTE: Step 7: Not Yet Implemented.
    lc.print_control("{{SUCCESS}} All Checks PASSED!")
    lc.dump_full_log()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Runs the precheck tool by calling the various checks in order.')

    parser.add_argument('--target_path', '-t', required=True,
                        help='Absolute Path to the project.')

    parser.add_argument('--output_directory', '-o', required=False,
                        help='Output Directory, defaults to /target_path/checks')

    parser.add_argument('--waive_fuzzy_checks', '-wfc', action='store_true', default=False,
                        help="Specifies whether or not to waive fuzzy consistency checks.")

    parser.add_argument('--skip_drc', '-sd', action='store_true', default=False,
                        help="Specifies whether or not to skip DRC checks.")

    parser.add_argument('--drc_only', '-do', action='store_true', default=False,
                        help="Specifies whether or not to only run DRC checks.")

    args = parser.parse_args()
    target_path = args.target_path
    skip_drc = args.skip_drc
    waive_fuzzy_checks = args.waive_fuzzy_checks
    drc_only = args.drc_only

    run_check_sequence(target_path, args.output_directory, waive_fuzzy_checks, skip_drc, drc_only)
