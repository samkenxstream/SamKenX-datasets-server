# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 The HuggingFace Authors.

import logging
from http import HTTPStatus
from typing import Any, List, Literal, Mapping, Optional, TypedDict, Union

from datasets import get_dataset_split_names
from datasets.data_files import EmptyDatasetError as _EmptyDatasetError
from libcommon.simple_cache import SplitFullName

from worker.job_runner import JobRunnerError
from worker.job_runners._datasets_based_job_runner import DatasetsBasedJobRunner

SplitNamesFromStreamingJobRunnerErrorCode = Literal[
    "EmptyDatasetError",
    "SplitNamesFromStreamingError",
]


class SplitNamesFromStreamingJobRunnerError(JobRunnerError):
    """Base class for split names job runner exceptions."""

    def __init__(
        self,
        message: str,
        status_code: HTTPStatus,
        code: SplitNamesFromStreamingJobRunnerErrorCode,
        cause: Optional[BaseException] = None,
        disclose_cause: bool = False,
    ):
        super().__init__(
            message=message, status_code=status_code, code=code, cause=cause, disclose_cause=disclose_cause
        )


class SplitNamesFromStreamingError(SplitNamesFromStreamingJobRunnerError):
    """Raised when the split names could not be fetched."""

    def __init__(self, message: str, cause: Optional[BaseException] = None):
        super().__init__(message, HTTPStatus.INTERNAL_SERVER_ERROR, "SplitNamesFromStreamingError", cause, True)


class EmptyDatasetError(SplitNamesFromStreamingJobRunnerError):
    """Raised when the dataset has no data."""

    def __init__(self, message: str, cause: Optional[BaseException] = None):
        super().__init__(message, HTTPStatus.INTERNAL_SERVER_ERROR, "EmptyDatasetError", cause, True)


class SplitNameItem(TypedDict):
    dataset: str
    config: str
    split: str


class SplitNamesFromStreamingResponseContent(TypedDict):
    split_names: List[SplitNameItem]


def compute_split_names_from_streaming_response(
    dataset: str,
    config: str,
    hf_token: Optional[str] = None,
) -> SplitNamesFromStreamingResponseContent:
    """
    Get the response of /split-names-from-streaming for one specific dataset and config on huggingface.co.
    Dataset can be private or gated if you pass an acceptable token.

    It is assumed that the dataset exists and can be accessed using the token, and that the config exists in
    the dataset.

    This function relies on the streaming mode if the splits are not directly defined in the dataset config. See
    https://github.dev/huggingface/datasets/blob/e183a269067575db8765ee979bd8523d14a1adae/src/datasets/inspect.py#L389-L390

    The /split-names-from-streaming response generated by this function does not include stats about the split,
    like the size or number of samples. See /dataset-info or /sizes for that.

    Args:
        dataset (`str`):
            A namespace (user or an organization) and a repo name separated
            by a `/`.
        config (`str`):
            A configuration name.
        hf_token (`str`, *optional*):
            An authentication token (See https://huggingface.co/settings/token)
    Returns:
        `SplitNamesFromStreamingResponseContent`: An object with the list of split names for the dataset and config.
    <Tip>
    Raises the following errors:
        - [`~job_runners.split_names.EmptyDatasetError`]
          The dataset is empty.
        - [`~job_runners.split_names.SplitsNamesError`]
          If the list of splits could not be obtained using the datasets library.
    </Tip>
    """
    logging.info(f"get split names for dataset={dataset}, config={config}")
    use_auth_token: Union[bool, str, None] = hf_token if hf_token is not None else False

    try:
        split_name_items: List[SplitNameItem] = [
            {"dataset": dataset, "config": config, "split": str(split)}
            for split in get_dataset_split_names(path=dataset, config_name=config, use_auth_token=use_auth_token)
        ]
    except _EmptyDatasetError as err:
        raise EmptyDatasetError("The dataset is empty.", cause=err) from err
    except Exception as err:
        raise SplitNamesFromStreamingError(
            f"Cannot get the split names for the config '{config}' of the dataset.",
            cause=err,
        ) from err
    return {"split_names": split_name_items}


class SplitNamesFromStreamingJobRunner(DatasetsBasedJobRunner):
    @staticmethod
    def get_job_type() -> str:
        return "/split-names-from-streaming"

    @staticmethod
    def get_version() -> str:
        return "1.0.0"

    def compute(self) -> Mapping[str, Any]:
        if self.config is None:
            raise ValueError("config is required")
        return compute_split_names_from_streaming_response(
            dataset=self.dataset, config=self.config, hf_token=self.common_config.hf_token
        )

    def get_new_splits(self, content: Mapping[str, Any]) -> set[SplitFullName]:
        """Get the set of new splits, from the content created by the compute."""
        return {
            SplitFullName(dataset=s["dataset"], config=s["config"], split=s["split"]) for s in content["split_names"]
        }
