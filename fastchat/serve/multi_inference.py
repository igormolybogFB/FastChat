"""
Use FastChat with Hugging Face generation APIs.

Usage:
python3 -m fastchat.serve.huggingface_api --model lmsys/vicuna-7b-v1.3
python3 -m fastchat.serve.huggingface_api --model lmsys/fastchat-t5-3b-v1.0
"""
import argparse
import json

import torch
from itertools import cycle
from tqdm import tqdm

from fastchat.model import load_model, get_conversation_template, add_model_args


@torch.inference_mode()
def generate(model, tokenizer, prompt, temperature, repetition_penalty, max_new_tokens, top_p, max_prompt_tokens):

    input_ids = tokenizer([prompt]).input_ids
    assert len(input_ids) < max_prompt_tokens, f"prompt {prompt} resulted in more tokens than --max-prompt-tokens value"

    output_ids = model.generate(
        torch.as_tensor(input_ids).cuda(),
        do_sample=True,
        temperature=temperature,
        repetition_penalty=repetition_penalty,
        max_new_tokens=max_new_tokens,
        top_p=top_p
    )

    if model.config.is_encoder_decoder:
        output_ids = output_ids[0]
    else:
        output_ids = output_ids[0][len(input_ids[0]) :]
    outputs = tokenizer.decode(
        output_ids, skip_special_tokens=True, spaces_between_special_tokens=False
    )

    return outputs

def dialog_to_prompt(conv, messages):
    
    roles = cycle(conv.roles)
    for role, message in zip(roles, messages):
        conv.append_message(role, message["content"])

    conv.append_message(conv.roles[1], None)

    return conv.get_prompt()


def main(args):

    with open(args.input_path, 'r') as input_file:
        dialogs_list = json.load(input_file)


    model, tokenizer = load_model(
                    args.model_path,
                    args.device,
                    args.num_gpus,
                    args.max_gpu_memory,
                    args.load_8bit,
                    args.cpu_offloading,
                    revision=args.revision,
                    debug=args.debug,
                )

    
    for dialog in tqdm(dialogs_list):
        conv_template = get_conversation_template(args.model_path)
        prompt = dialog_to_prompt(conv_template, dialog["messages"])

        if not "generation" in dialog.keys():
            try: 
                dialog["generation"] = generate(model, tokenizer, prompt,
                                    temperature=args.temperature,
                                    repetition_penalty=args.repetition_penalty,
                                    max_new_tokens=args.max_new_tokens,
                                    top_p=args.top_p,
                                    max_prompt_tokens=args.max_prompt_tokens)
                with open(args.output_path, 'w') as output_file:
                    json.dump(dialogs_list, output_file)
            except Exception as e:
                print(f"Error: {e} while processing the prompt: {prompt} ")

    with open(args.output_path, 'w') as output_file:
        json.dump(dialogs_list, output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_model_args(parser)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--repetition_penalty", type=float, default=1.0)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--input_path", type=str)
    parser.add_argument("--output_path", type=str)
    parser.add_argument("--max-prompt-tokens", type=int, default=1024)
    parser.add_argument("--top_p", type=float, default=0.9)
    # compatability with stool
    parser.add_argument("--dump_dir", type=str, default="")
    args = parser.parse_args()

    # Reset default repetition penalty for T5 models.
    if "t5" in args.model_path and args.repetition_penalty == 1.0:
        args.repetition_penalty = 1.2

    main(args)
