from __future__ import annotations

import logging
import sys
import datetime
import os
import timeit

from typing import Iterable, List, Optional
from pathlib import Path
import json

from .context import PipelineContext
from .stage import PipelineStage
from .parameters import Parameters, print_options
from .site_parameters import resolve_site_parameters

from . import checkpoints

logger = logging.getLogger(__name__)


class PipelineRunner:
    """
    Executes a sequence of pipeline stages.

    Responsibilities:
    - Honor each stage's should_run predicate.
    - Run/log each stage in order and surface progress markers for UIs.
    - Leave populated context for downstream consumers.
    """

    def __init__(self, stages: Iterable[PipelineStage]):
        self.stages: List[PipelineStage] = list(stages)

    def run(self, context: PipelineContext) -> None:
        start_time = timeit.default_timer()
        last_time = start_time
        with open(context.config_path, encoding="utf-8") as f:
            params = resolve_site_parameters(json.load(f))

        if params.logging_level != "none":
            self.init_log_file(context, params)
        total_stages = len(self.stages)
        if total_stages == 0:
            print("PROGRESS: 100%")
            return

        for idx, stage in enumerate(self.stages):
            ran = False
            if not stage.should_run(context, params):
                logger.info("Skipping stage %s", stage.name)
            else:
                checkpoints.save_context(context, stage.name)
                print(f"RUNNING: {stage.name}")
                stage.log_start()
                stage.run(context, params)
                stage.log_end()
                ran = True

            pct = int(((idx + 1) / total_stages) * 100)
            t = timeit.default_timer()
            time_passed = str(datetime.timedelta(seconds = t - last_time))
            print(f"STAGE: {stage.name} ({'done' if ran else 'skipped'}) in {time_passed}")
            print(f"PROGRESS: {pct}%")
            last_time = t

        time_passed = str(datetime.timedelta(seconds = timeit.default_timer() - start_time))
        print(f"Completed analysis for site: {context.global_settings['sitename']} in {time_passed}")
        
        if params.logging_level == "all":
            self.close_log_file()


    def init_log_file(self, context: PipelineContext, params: Parameters):
        sitename, output_dir = self.parse_config(context)
        
        # set up log file
        filename = output_dir + "/log_" + datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + ".txt"
        os.makedirs(output_dir, exist_ok=True)
        sys.stdout = open(filename, "w", buffering=1)

        # print initial info
        print("=" * 10 + "Sitename" + "=" * 10)
        print(f"sitename: {sitename}\n")
        print("=" * 10 + "Parameters" + "=" * 10)
        params.print_params()
        print()
        print("=" * 10 + "Options" + "=" * 10)
        print_options()
        print()

        # close log file and reset stdout if done
        if params.logging_level == "params":
            self.close_log_file()
        else:
            print("=" * 10 + "Output" + "=" * 10)


    # close log file and reset stdout
    def close_log_file(self):
        sys.stdout.close()
        sys.stdout = sys.__stdout__
    

    # this is doing work twice (config is parsed in config stage), but its the simplest way to get sitename
    # before the pipeline starts
    def parse_config(self, context):
        config_path = Path(context.config_path).expanduser().resolve()
        with open(config_path, "r") as f:
            config = json.load(f)
        sitename = config.get("inputs", {}).get("sitename", "no sitename given")
        output_dir = str((config_path.parent / config["output_dir"] / "logs").resolve())
        return sitename, output_dir


def run_pipeline(context: PipelineContext, stages: Iterable[PipelineStage]) -> PipelineContext:
    runner = PipelineRunner(stages)
    runner.run(context)
    return context
