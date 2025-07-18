# 2.0 hashes Updated by HammyCatte

# Originally written by petrascyll
# Thanks to Leotorrez, CaveRabbit, and SilentNightSound for help
# Join AGMG: discord.gg/agmg

import os
import re
import time
import struct
import argparse
import traceback

from dataclasses import dataclass, field
from pathlib import Path

# extra precaution to not 'fix' 
# the same buffer multiple times
global_modified_buffers: dict[str, list[str]] = {}


def main():
    parser = argparse.ArgumentParser(
        prog="ZZZ Fix 2.0 by HammyCatte",
        description=('')
    )

    parser.add_argument('ini_filepath', nargs='?', default=None, type=str)
    args = parser.parse_args()

    if args.ini_filepath:
        if args.ini_filepath.endswith('.ini'):
            print('Passed .ini file:', args.ini_filepath)
            upgrade_ini(args.ini_filepath)
        else:
            raise Exception('Passed file is not an Ini')

    else:
        # Change the CWD to the directory this script is in
        # Nuitka: "Onefile: Finding files" in https://nuitka.net/doc/user-manual.pdf 
        # I'm not using Nuitka anymore but this distinction (probably) also applies for pyinstaller
        # os.chdir(os.path.abspath(os.path.dirname(sys.argv[0])))
        print('CWD: {}'.format(os.path.abspath('.')))
        process_folder('.')

    print('Done!')


# SHAMELESSLY (mostly) ripped from genshin fix script
def process_folder(folder_path):
    for filename in os.listdir(folder_path):
        if filename.upper().startswith('DISABLED') and filename.lower().endswith('.ini'):
            continue
        if filename.upper().startswith('DESKTOP'):
            continue

        filepath = os.path.join(folder_path, filename)
        if os.path.isdir(filepath):
            process_folder(filepath)
        elif filename.endswith('.ini'):
            print('Found .ini file:', filepath)
            upgrade_ini(filepath)


def upgrade_ini(filepath):
    try:
        # Errors occuring here is fine as no write operations to the ini nor any buffers are performed
        ini = Ini(filepath).upgrade()
    except Exception as x:
        print('Error occurred: {}'.format(x))
        print('No changes have been applied to {}!'.format(filepath))
        print()
        print(traceback.format_exc())
        print()
        return False

    try:
        # Content of the ini and any modified buffers get written to disk in this function
        # Since the code for this function is more concise and predictable, the chance of it failing
        # is low, but it can happen if Windows doesn't want to cooperate and write for whatever reason.
        ini.save()
    except Exception as X:
        print('Fatal error occurred while saving changes for {}!'.format(filepath))
        print('Its likely that your mod has been corrupted. You must redownload it from the source before attempting to fix it again.')
        print()
        print(traceback.format_exc())
        print()
        return False

    return True


# MARK: Ini
class Ini():
    def __init__(self, filepath):
        self.filepath = filepath
        try:
            self.content  = Path(self.filepath).read_text(encoding='utf-8')
            self.encoding = 'utf-8'
        except UnicodeDecodeError:
            self.content  = Path(self.filepath).read_text(encoding='gb2312')
            self.encoding = 'gb2312'
        

        # The random ordering of sets is annoying
        # Use a list for the hashes that will be iterated on
        # and a set for the hashes I already iterated on
        self._hashes = []
        self._touched = False
        self._done_hashes = set()

        # Only write the modified buffers at the very end after the ini is saved, since
        # the ini can be backed up, while backing up buffers is not not reasonable.
        # Buffer with multiple fixes: will be read from the mod directory for the first
        # fix, and from this dict in memory for subsequent fixes 
        self.modified_buffers = {
            # buffer_filepath: buffer_data
        }

        # Get all (uncommented) hashes in the ini
        pattern = re.compile(r'\n\s*hash\s*=\s*([a-f0-9]*)', flags=re.IGNORECASE)
        self._hashes = pattern.findall(self.content)
    
    def upgrade(self):
        while len(self._hashes) > 0:
            hash = self._hashes.pop()
            if hash not in self._done_hashes:
                if hash in hash_commands:
                    print(f'\tProcessing {hash}:')
                    default_args = DefaultArgs(hash=hash, ini=self, data={}, tabs=2)
                    self.execute(hash_commands[hash], default_args)
                else:
                    print(f'\tSkipping {hash}: No tasks available')
            else:
                print(f'\tSkipping {hash}: Already Checked/Processed')

            self._done_hashes.add(hash)

        return self

    def execute(self, commands, default_args):
        for command in commands:
            clss = command[0]
            args = command[1] if len(command) > 1 else {}
            instance = clss(**args) if type(args) is dict else clss(*args) 
            result: ExecutionResult = instance.execute(default_args)

            self._touched = self._touched or result.touched
            if result.failed:
                print()
                return

            if result.queue_hashes:
                # Only add the hashes that I haven't already iterated on
                self._hashes.extend(set(result.queue_hashes).difference(self._done_hashes))

            if result.queue_commands:
                # sub_default_args = DefaultArgs(
                #     hash = default_args.hash,
                #     ini  = default_args.ini,
                #     data = default_args.data,
                #     tabs = default_args.tabs
                # )
                self.execute(result.queue_commands, default_args)

            if result.signal_break:
                return

        return default_args

    def save(self):
        if self._touched:
            basename = os.path.basename(self.filepath).split('.ini')[0]
            dir_path = os.path.abspath(self.filepath.split(basename+'.ini')[0])
            backup_filename = f'DISABLED_BACKUP_{int(time.time())}.{basename}.ini'
            backup_fullpath = os.path.join(dir_path, backup_filename)

            os.rename(self.filepath, backup_fullpath)
            print(f'Created Backup: {backup_filename} at {dir_path}')
            with open(self.filepath, 'w', encoding=self.encoding) as updated_ini:
                updated_ini.write(self.content)
            # with open('DISABLED_BACKUP_debug.ini', 'w', encoding='utf-8') as updated_ini:
            #     updated_ini.write(self.content)

            if len(self.modified_buffers) > 0:
                print('Writing updated buffers')
                for filepath, data in self.modified_buffers.items():
                    with open(filepath, 'wb') as f:
                        f.write(data)
                    print('\tSaved: {}'.format(filepath))

            print('Updates applied')
        else:
            print('No changes applied')
        print()

    def has_hash(self, hash):
        return (
            (hash in self._hashes)
            or (hash in self._done_hashes)
        )


# MARK: Commands

def get_critical_content(section):
    hash = None
    match_first_index = None
    critical_lines = []
    pattern = re.compile(r'^\s*(.*?)\s*=\s*(.*?)\s*$', flags=re.IGNORECASE)

    for line in section.splitlines():
        line_match = pattern.match(line)
        
        if line.strip().startswith('['):
            continue
        elif line_match and line_match.group(1).lower() == 'hash':
            hash = line_match.group(2)
        elif line_match and line_match.group(1).lower() == 'match_first_index':
            match_first_index = line_match.group(2)
        else:
            critical_lines.append(line)

    return '\n'.join(critical_lines), hash, match_first_index


# Returns all resources used by a commandlist
# Hardcoded to only return vb1 i.e. texcoord resources for now
# (TextureOverride sections are special commandlists)
def process_commandlist(ini_content: str, commandlist: str, target: str):
    line_pattern = re.compile(r'^\s*(run|{})\s*=\s*(.*)\s*$'.format(target), flags=re.IGNORECASE)
    resources = []

    for line in commandlist.splitlines():
        line_match = line_pattern.match(line)
        if not line_match: continue

        if line_match.group(1) == target:
            resources.append(line_match.group(2))

        # Must check the commandlists that are run within the
        # the current commandlist for the resource as well
        # Recursion yay
        elif line_match.group(1) == 'run':
            commandlist_title = line_match.group(2)
            pattern = get_section_title_pattern(commandlist_title)
            commandlist_match = pattern.search(ini_content + '\n[')
            if commandlist_match:
                sub_resources = process_commandlist(ini_content, commandlist_match.group(1), target)
                resources.extend(sub_resources)

    return resources


@dataclass
class DefaultArgs():
    hash : str
    ini  : Ini
    tabs : int
    data : dict[str, str]


@dataclass
class ExecutionResult():
    touched        : bool = False
    failed         : bool = False
    signal_break   : bool = False
    queue_hashes   : tuple[str] = None
    queue_commands : tuple[str] = None


@dataclass(init=False)
class log():
    text: tuple[str]

    def __init__(self, *text):
        self.text = text

    def execute(self, default_args: DefaultArgs):
        tabs        = default_args.tabs

        info  = self.text[0]
        hash  = self.text[1] if len(self.text) > 1 else ''
        title = self.text[2] if len(self.text) > 2 else ''
        rest  = self.text[3:] if len(self.text) > 3 else []

        s = '{}{:34}'.format('\t'*tabs, info)
        if hash  : s += ' - {:8}'.format(hash)
        if title : s += ' - {}'.format(title) 
        if rest  : s += ' - '.join(rest)

        print(s)

        return ExecutionResult(
            touched        = False,
            failed         = False,
            signal_break   = False,
            queue_hashes   = None,
            queue_commands = None
        )


@dataclass
class update_hash():
    new_hash: str

    def execute(self, default_args: DefaultArgs):
        ini         = default_args.ini
        active_hash = default_args.hash

        pattern = re.compile(r'(\n\s*)(hash\s*=\s*{})'.format(active_hash), flags=re.IGNORECASE)
        ini.content, sub_count = pattern.subn(r'\1hash = {}\n; \2'.format(self.new_hash), ini.content)

        default_args.hash = self.new_hash

        return ExecutionResult(
            touched        = True,
            failed         = False,
            signal_break   = False,
            queue_hashes   = (self.new_hash,),
            queue_commands = (
                (log, ('+ Updating {} hash(es) to {}'.format(sub_count, self.new_hash),)),
            )
        )


@dataclass
class comment_sections():

    def execute(self, default_args: DefaultArgs):
        ini  = default_args.ini
        hash = default_args.hash

        pattern = get_section_hash_pattern(hash)
        new_ini_content = ''   # ini content with all matching sections commented

        prev_j = 0
        commented_count = 0
        section_matches = pattern.finditer(ini.content)
        for section_match in section_matches:
            i, j = section_match.span(1)
            commented_section = '\n'.join(['; ' + line for line in section_match.group(1).splitlines()])
            commented_count  += 1

            new_ini_content += ini.content[prev_j:i] + commented_section
            prev_j = j

        new_ini_content += ini.content[prev_j:]
        
        ini.content = new_ini_content

        return ExecutionResult(
            touched        = True,
            failed         = False,
            signal_break   = False,
            queue_hashes   = None,
            queue_commands = (
                (log, ('- Commented {} relevant section(s)'.format(commented_count),)),
            )
        )


@dataclass
class comment_commandlists():
    commandlist_title: str

    def execute(self, default_args: DefaultArgs):
        ini  = default_args.ini

        pattern = get_section_title_pattern(self.commandlist_title)
        new_ini_content = ''   # ini content with matching commandlist commented out

        prev_j = 0
        commented_count = 0
        commandlist_matches = pattern.finditer(ini.content)
        for commandlist_match in commandlist_matches:
            i, j = commandlist_match.span(1)
            commented_commandlist = '\n'.join(['; ' + line for line in commandlist_match.group(1).splitlines()])
            commented_count  += 1

            new_ini_content += ini.content[prev_j:i] + commented_commandlist
            prev_j = j

        new_ini_content += ini.content[prev_j:]
        
        ini.content = new_ini_content

        return ExecutionResult(
            touched        = True,
            failed         = False,
            signal_break   = False,
            queue_hashes   = None,
            queue_commands = (
                (log, ('- Commented {} relevant commandlist(s)'.format(commented_count),)),
            )
        )


@dataclass(kw_only=True)
class remove_section():
    capture_content : str = None
    capture_position: str = None

    def execute(self, default_args: DefaultArgs):
        ini         = default_args.ini
        active_hash = default_args.hash
        data        = default_args.data

        pattern = get_section_hash_pattern(active_hash)
        section_match = pattern.search(ini.content)
        if not section_match: raise Exception('Bad regex')
        start, end = section_match.span(1)

        if self.capture_content:
            data[self.capture_content] = get_critical_content(section_match.group(1))[0]
        if self.capture_position:
            data[self.capture_position] = str(start)

        ini.content = ini.content[:start] + ini.content[end:]

        return ExecutionResult(
            touched        = True,
            failed         = False,
            signal_break   = False,
            queue_hashes   = None,
            queue_commands = None
        )


@dataclass(kw_only=True)
class remove_indexed_sections():
    capture_content         : str = None
    capture_indexed_content : str = None
    capture_position        : str = None

    def execute(self, default_args: DefaultArgs):
        ini  = default_args.ini
        hash = default_args.hash
        data = default_args.data
        
        pattern = get_section_hash_pattern(hash)
        new_ini_content = ''   # ini with ib sections removed
        position        = -1   # First Occurence Deletion Start Position
        prev_end         = 0

        section_matches = pattern.finditer(ini.content)
        for section_match in section_matches:
            if re.search(r'\n\s*match_first_index\s*=', section_match.group(1), flags=re.IGNORECASE):
                if self.capture_indexed_content:
                    critical_content, _, match_first_index = get_critical_content(section_match.group(1))
                    placeholder = '{}{}{}'.format(self.capture_indexed_content, match_first_index, self.capture_indexed_content)
                    data[placeholder] = critical_content
            else:
                if self.capture_content:
                    critical_content = get_critical_content(section_match.group(1))[0]
                    placeholder = self.capture_content
                    data[placeholder] = critical_content

            start, end = section_match.span()
            if position == -1:
                position = start

            new_ini_content += ini.content[prev_end:start]
            prev_end = end

        new_ini_content += ini.content[prev_end:]
        ini.content = new_ini_content

        if self.capture_position:
            data[self.capture_position] = str(position)

        return ExecutionResult(
            touched        = True,
            failed         = False,
            signal_break   = False,
            queue_hashes   = None,
            queue_commands = None
        )


@dataclass(kw_only=True)
class capture_section():
    capture_content  : str = None
    capture_position : str = None

    def execute(self, default_args: DefaultArgs):
        ini         = default_args.ini
        active_hash = default_args.hash
        data        = default_args.data

        pattern = get_section_hash_pattern(active_hash)
        section_match = pattern.search(ini.content)
        if not section_match: raise Exception('Bad regex')
        _, end = section_match.span(1)

        if self.capture_content:
            data[self.capture_content] = get_critical_content(section_match.group(1))[0]
        if self.capture_position:
            data[self.capture_position] = str(end + 1)

        return ExecutionResult(
            touched        = False,
            failed         = False,
            signal_break   = False,
            queue_hashes   = None,
            queue_commands = None
        )


@dataclass(kw_only=True)
class create_new_section():
    section_content  : str
    saved_position   : str = None
    capture_position : str = None

    def execute(self, default_args: DefaultArgs):
        ini         = default_args.ini
        data        = default_args.data

        pos = -1
        if self.saved_position and self.saved_position in data:
            pos = int(data[self.saved_position])

        for placeholder, value in data.items():
            if placeholder.startswith('_'):
                # conditions are not to be used for substitution
                continue
            self.section_content = self.section_content.replace(placeholder, value)

        # Half broken/fixed mods' ini will not have the object indices we're expecting
        # Could also be triggered due to a typo in the hash commands
        for emoji in ['🍰', '🌲', '🤍']:
            if emoji in self.section_content:
                print('Section substitution failed')
                print(self.section_content)
                return ExecutionResult(
                    touched        = False,
                    failed         = True,
                    signal_break   = False,
                    queue_hashes   = None,
                    queue_commands = None
                )
  
        if self.capture_position:
            data[self.capture_position] = str(len(self.section_content) + pos)

        ini.content = ini.content[:pos] + self.section_content + ini.content[pos:]

        return ExecutionResult(
            touched        = True,
            failed         = False,
            signal_break   = False,
            queue_hashes   = None,
            queue_commands = None
        )


@dataclass(kw_only=True)
class transfer_indexed_sections():
    trg_indices: tuple[str] = None
    src_indices: tuple[str] = None

    def execute(self, default_args: DefaultArgs):
        ini         = default_args.ini
        hash        = default_args.hash

        title = None
        p = get_section_hash_pattern(hash)
        ib_matches = p.findall(ini.content)
        indexed_ib_count = 0
        for m in ib_matches:
            if re.search(r'\n\s*match_first_index\s*=', m):
                indexed_ib_count += 1
                if not title: title = re.match(r'^\[TextureOverride(.*?)\]', m, flags=re.IGNORECASE).group(1)[:-1]
            else:
                if not title: title = re.match(r'^\[TextureOverride(.*?)\]', m, flags=re.IGNORECASE).group(1)[:-2]

        if indexed_ib_count == 0:
            return ExecutionResult()

        unindexed_ib_content = '\n'.join([
            f'[TextureOverride{title}IB]',
            f'hash = {hash}',
            '🍰',
            '',
            ''
        ])

        alpha = [
            'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
            'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T',
            'U', 'V', 'W', 'X', 'Y', 'Z'
        ]
        content = ''
        for i, (trg_index, src_index) in enumerate(zip(self.trg_indices, self.src_indices)):
            content += '\n'.join([
                f'[TextureOverride{title}{alpha[i]}]',
                f'hash = {hash}',
                f'match_first_index = {trg_index}',
                f'🤍{src_index}🤍' if src_index != '-1' else 'ib = null',
                '',
                ''
            ])

        return ExecutionResult(
            touched        = False,
            failed         = False,
            signal_break   = False,
            queue_hashes   = None,
            queue_commands = (
                (remove_indexed_sections, {'capture_content': '🍰', 'capture_indexed_content': '🤍', 'capture_position': '🌲'}),
                (create_new_section,      {'saved_position': '🌲', 'section_content': content}),
                (create_new_section,      {'saved_position': '🌲', 'section_content': unindexed_ib_content}),
            ) if indexed_ib_count < len(ib_matches) else (
                (remove_indexed_sections, {'capture_indexed_content': '🤍', 'capture_position': '🌲'}),
                (create_new_section,      {'saved_position': '🌲', 'section_content': content}),
            ),
        )


@dataclass()
class multiply_section_if_missing():
    equiv_hashes: tuple[str] | str
    extra_title : tuple[str]

    def execute(self, default_args: DefaultArgs):
        ini  = default_args.ini

        if (type(self.equiv_hashes) is not tuple):
            self.equiv_hashes = (self.equiv_hashes,)
        for equiv_hash in self.equiv_hashes:
            if ini.has_hash(equiv_hash):
                return ExecutionResult(
                    touched        = False,
                    failed         = False,
                    signal_break   = False,
                    queue_hashes   = None,
                    queue_commands = (
                        (log, ('/ Skipping Section Multiplication',  f'{equiv_hash}', f'[...{self.extra_title}]',)),
                    ),
                )
        equiv_hash = self.equiv_hashes[0]

        content = '\n'.join([
            '',
            f'[TextureOverride{self.extra_title}]',
            f'hash = {equiv_hash}',
            '🍰',
            '',
        ])

        return ExecutionResult(
            touched        = False,
            failed         = False,
            signal_break   = False,
            queue_hashes   = (equiv_hash,),
            queue_commands = (
                (log,                ('+ Multiplying Section', f'{equiv_hash}', f'[...{self.extra_title}]')),
                (capture_section,    {'capture_content': '🍰', 'capture_position': '🌲'}),
                (create_new_section, {'saved_position': '🌲', 'section_content': content}),
            ),
        )


@dataclass()
class add_ib_check_if_missing():

    def execute(self, default_args: DefaultArgs):
        ini  = default_args.ini
        hash = default_args.hash
        
        pattern         = get_section_hash_pattern(hash)
        section_matches = pattern.finditer(ini.content)

        needs_check       = False
        new_sections      = ''
        unindexed_section = ''

        for section_match in section_matches:
            if not re.search(r'\n\s*match_first_index\s*=', section_match.group(1), flags=re.IGNORECASE):
                unindexed_section = section_match.group()
                continue

            if re.search(r'\n\s*run\s*=\s*CommandListSkinTexture', section_match.group(1), flags=re.IGNORECASE):
                new_sections += section_match.group()
                continue

            needs_check = True
            new_sections += re.sub(
                r'\n\s*match_first_index\s*=.*?\n',
                r'\g<0>run = CommandListSkinTexture\n',
                section_match.group(),
                flags=re.IGNORECASE, count=1
            )


        if unindexed_section and not new_sections:
            if not re.search(r'\n\s*run\s*=\s*CommandListSkinTexture', unindexed_section, flags=re.IGNORECASE):
                needs_check = True
                unindexed_section = re.sub(
                    r'\n\s*hash\s*=.*?\n',
                    r'\g<0>run = CommandListSkinTexture\n',
                    unindexed_section,
                    flags=re.IGNORECASE, count=1
                )

        new_sections = unindexed_section + new_sections

        return ExecutionResult(
            touched        = False,
            failed         = False,
            signal_break   = False,
            queue_hashes   = None,
            queue_commands = (
                (log,                     ('+ Adding `run = CommandListSkinTexture`',)),
                (remove_indexed_sections, {'capture_position': '🌲'}),
                (create_new_section,      {'saved_position': '🌲', 'section_content': new_sections}),
            ) if needs_check else (
                (log,                     ('/ Skipping `run = CommandListSkinTexture` Addition',)),
            ),
        )


@dataclass
class add_section_if_missing():
    equiv_hashes    : tuple[str] | str
    section_title   : str = None
    section_content : str = field(default='')

    def execute(self, default_args: DefaultArgs):
        ini = default_args.ini

        if (type(self.equiv_hashes) is not tuple):
            self.equiv_hashes = (self.equiv_hashes,)
        for equiv_hash in self.equiv_hashes:
            if ini.has_hash(equiv_hash):
                return ExecutionResult(
                    touched        = False,
                    failed         = False,
                    signal_break   = False,
                    queue_hashes   = None,
                    queue_commands = (
                        (log, ('/ Skipping Section Addition', equiv_hash, f'[...{self.section_title}]',)),
                    ),
                )
        equiv_hash = self.equiv_hashes[0]

        section = '\n[TextureOverride{}]\n'.format(self.section_title)
        section += 'hash = {}\n'.format(equiv_hash)
        section += self.section_content

        return ExecutionResult(
            touched        = False,
            failed         = False,
            signal_break   = False,
            queue_hashes   = (equiv_hash,),
            queue_commands = (
                (log,                ('+ Adding Section', equiv_hash, f'[...{self.section_title}]',)),
                (capture_section,    {'capture_position': '🌲'}),
                (create_new_section, {'saved_position': '🌲', 'section_content': section}),
            ),
        )


@dataclass
class zzz_13_remap_texcoord():
    id: str
    old_format: tuple[str] # = ('4B','2e','2f','2e')
    new_format: tuple[str] # = ('4B','2f','2f','2f')

    def execute(self, default_args: DefaultArgs):
        ini  = default_args.ini
        hash = default_args.hash
        tabs = default_args.tabs

        # Precompute new buffer strides and offsets
        # Check if existing buffer stride matches our expectations
        # before remapping it
        if (len(self.old_format) != len(self.new_format)): raise Exception()
        old_stride = struct.calcsize('<' + ''.join(self.old_format))
        new_stride = struct.calcsize('<' + ''.join(self.new_format))

        offset = 0
        offsets = [0]
        for format_chunk in self.old_format:
            offset += struct.calcsize(f'<{format_chunk}')
            offsets.append(offset)

        # Debugging
        # print(f'\t\tOld Format stride: {struct.calcsize('<' + ''.join(self.old_format))}')
        # print(f'\t\tNew Format stride: {struct.calcsize('<' + ''.join(self.new_format))}')
        # print(f'\t\tBuffer Stride: {stride}')
        # print(f'\t\tOffsets: {offsets}')

        # Need to find all Texcoord Resources used by this hash directly
        # through TextureOverrides or run through Commandlists... 
        pattern = get_section_hash_pattern(hash)
        section_match = pattern.search(ini.content)
        resources = process_commandlist(ini.content, section_match.group(1), 'vb1')

        # - Match Resource sections to find filenames of buffers 
        # - Update stride value of resources early instead of iterating again later
        buffer_filenames = set()
        line_pattern = re.compile(r'^\s*(filename|stride)\s*=\s*(.*)\s*$', flags=re.IGNORECASE)
        for resource in resources:
            pattern = get_section_title_pattern(resource)
            resource_section_match = pattern.search(ini.content)
            if not resource_section_match: continue

            modified_resource_section = []
            for line in resource_section_match.group(1).splitlines():
                line_match = line_pattern.match(line)
                if not line_match:
                    modified_resource_section.append(line)

                # Capture buffer filename
                elif line_match.group(1) == 'filename':
                    modified_resource_section.append(line)
                    buffer_filenames.add(line_match.group(2))

                # Update stride value of resource in ini
                elif line_match.group(1) == 'stride':
                    stride = int(line_match.group(2))
                    if stride != old_stride:
                        print('{}X WARNING [{}]! Expected buffer stride {} but got {} instead. Overriding and continuing.'.format('\t'*tabs, resource, old_stride, stride))
                    #     raise Exception('Remap failed for {}! Expected buffer stride {} but got {} instead.'.format(resource, old_stride, stride))

                    modified_resource_section.append('stride = {}'.format(new_stride))
                    modified_resource_section.append(';'+line)

            # Update ini
            modified_resource_section = '\n'.join(modified_resource_section)
            i, j = resource_section_match.span(1)
            ini.content = ini.content[:i] + modified_resource_section + ini.content[j:]

        global global_modified_buffers
        for buffer_filename in buffer_filenames:
            buffer_filepath = Path(Path(ini.filepath).parent/buffer_filename)
            buffer_dict_key = str(buffer_filepath.absolute())

            if buffer_dict_key not in global_modified_buffers:
                global_modified_buffers[buffer_dict_key] = []
            fix_id = f'{self.id}-texcoord_remap'
            if fix_id in global_modified_buffers[buffer_dict_key]: continue
            else: global_modified_buffers[buffer_dict_key].append(fix_id)

            if buffer_dict_key not in ini.modified_buffers:
                buffer = buffer_filepath.read_bytes()
            else:
                buffer = ini.modified_buffers[buffer_dict_key]

            vcount = len(buffer) // stride
            new_buffer = bytearray()
            for i in range(vcount):
                for j, (old_chunk, new_chunk) in enumerate(zip(self.old_format, self.new_format)):

                    if offsets[j] < stride and offsets[j+1] <= stride:

                        if old_chunk != new_chunk:
                            # HardCode VColor Remap
                            if (j == 0 and old_chunk == '4B' and new_chunk == '4f'):
                                new_buffer.extend(struct.pack('<4f', *[b/255 for b in struct.unpack_from('<4B', buffer, i*stride + 0)]))
                            elif (j == 0 and old_chunk == '4f' and new_chunk == '4B'):
                                new_buffer.extend(struct.pack('<4B', *[int(b*255) for b in struct.unpack_from('<4f', buffer, i*stride + 0)]))

                            # General Element Remap
                            else:
                                new_buffer.extend(struct.pack(f'<{new_chunk}', *struct.unpack_from(f'<{old_chunk}', buffer, i*stride+offsets[j])))

                        # No Element Remap Needed
                        else:
                            new_buffer.extend(buffer[i*stride + offsets[j]: i*stride + offsets[j+1]])

                    # Mod texcoord vertex data does not saturate the expected old stride
                    else: # cope
                        new_buffer.extend(struct.pack(f'<{new_chunk}', *([0] * int(new_chunk[0]))))
            
            ini.modified_buffers[buffer_dict_key] = new_buffer    

        return ExecutionResult(
            touched=True
        )


# Deprecated. Use generalized remap_texcoord instead
@dataclass
class zzz_12_shrink_texcoord_color():
    id: str

    def execute(self, default_args: DefaultArgs):
        ini  = default_args.ini
        hash = default_args.hash
        tabs = default_args.tabs        

        # Need to find all Texcoord Resources used by this hash directly
        # through TextureOverrides or run through Commandlists... 
        pattern = get_section_hash_pattern(hash)
        section_match = pattern.search(ini.content)
        resources = process_commandlist(ini.content, section_match.group(1), 'vb1')

        # - Match Resource sections to find filenames of buffers 
        # - Update stride value of resources early instead of iterating again later
        buffer_filenames = set()
        line_pattern = re.compile(r'^\s*(filename|stride)\s*=\s*(.*)\s*$', flags=re.IGNORECASE)
        for resource in resources:
            pattern = get_section_title_pattern(resource)
            resource_section_match = pattern.search(ini.content)
            if not resource_section_match: continue

            modified_resource_section = []
            for line in resource_section_match.group(1).splitlines():
                line_match = line_pattern.match(line)
                if not line_match:
                    modified_resource_section.append(line)

                # Capture buffer filename
                elif line_match.group(1) == 'filename':
                    modified_resource_section.append(line)
                    buffer_filenames.add(line_match.group(2))

                # Update stride value of resource in ini
                elif line_match.group(1) == 'stride':
                    stride = int(line_match.group(2))
                    modified_resource_section.append('stride = {}'.format(stride - 12))
                    modified_resource_section.append(';'+line)

            # Update ini
            modified_resource_section = '\n'.join(modified_resource_section)
            i, j = resource_section_match.span(1)
            ini.content = ini.content[:i] + modified_resource_section + ini.content[j:]

        global global_modified_buffers
        for buffer_filename in buffer_filenames:
            buffer_filepath = Path(Path(ini.filepath).parent/buffer_filename)
            buffer_dict_key = str(buffer_filepath.absolute())

            if buffer_dict_key not in global_modified_buffers:
                global_modified_buffers[buffer_dict_key] = []
            fix_id = f'{self.id}-zzz_12_shrink_texcoord_color'
            if fix_id in global_modified_buffers[buffer_dict_key]: continue
            else: global_modified_buffers[buffer_dict_key].append(fix_id)

            if buffer_dict_key not in ini.modified_buffers:
                buffer = buffer_filepath.read_bytes()
            else:
                buffer = ini.modified_buffers[buffer_dict_key]

            vcount = len(buffer) // stride
            new_buffer = bytearray()
            for i in range(vcount):
                # print(*[ int((f*255)) for f in struct.unpack_from('<4f', buffer, i*stride + 0)])
                new_buffer.extend(struct.pack(
                        '<4B',
                        *[
                            int(f * 255)
                            for f in struct.unpack_from('<4f', buffer, i*stride + 0)
                        ]
                    ))
                new_buffer.extend(buffer[i*stride + 16: i*stride + stride])
            
            ini.modified_buffers[buffer_dict_key] = new_buffer            

        return ExecutionResult(
            touched=True
        )

@dataclass
class update_buffer_blend_indices():
    hash       : str
    old_indices: tuple[int]
    new_indices: tuple[int]

    def execute(self, default_args: DefaultArgs):
        ini  = default_args.ini

        # Need to find all Texcoord Resources used by this hash directly
        # through TextureOverrides or run through Commandlists... 
        pattern = get_section_hash_pattern(self.hash)
        section_match = pattern.search(ini.content)
        resources = process_commandlist(ini.content, section_match.group(1), 'vb2')

        # - Match Resource sections to find filenames of buffers 
        # - Update stride value of resources early instead of iterating again later
        buffer_filenames = set()
        line_pattern = re.compile(r'^\s*(filename|stride)\s*=\s*(.*)\s*$', flags=re.IGNORECASE)
        for resource in resources:
            pattern = get_section_title_pattern(resource)
            resource_section_match = pattern.search(ini.content)
            if not resource_section_match: continue

            modified_resource_section = []
            for line in resource_section_match.group(1).splitlines():
                line_match = line_pattern.match(line)
                if not line_match:
                    modified_resource_section.append(line)

                # Capture buffer filename
                elif line_match.group(1) == 'filename':
                    modified_resource_section.append(line)
                    buffer_filenames.add(line_match.group(2))

        for buffer_filename in buffer_filenames:
            buffer_filepath = Path(Path(ini.filepath).parent/buffer_filename)
            buffer_dict_key = str(buffer_filepath.absolute())

            if buffer_dict_key not in ini.modified_buffers:
                buffer = buffer_filepath.read_bytes()
            else:
                buffer = ini.modified_buffers[buffer_dict_key]
    
            new_buffer = bytearray()
            blend_stride = 32
            vertex_count = len(buffer)//blend_stride
            for i in range(vertex_count):
                blend_weights  = struct.unpack_from('<4f', buffer, i*blend_stride + 0)
                blend_indices  = struct.unpack_from('<4I', buffer, i*blend_stride + 16)

                new_buffer.extend(struct.pack('<4f4I', *blend_weights, *[
                    vgx if vgx not in self.old_indices
                    else self.new_indices[self.old_indices.index(vgx)]
                    for vgx in blend_indices
                ]))

            ini.modified_buffers[buffer_dict_key] = new_buffer

        return ExecutionResult(
            touched=True
        )

@dataclass
class convert_to_slots():
    hash        : str              # = IB HASH
    slot_hashes : dict[int, tuple] # = {
    #     SLOT: [list of texture hashes that go in this slot...],
    #     ...
    # }
    '''
    If a slot is already overriden in the ib section, then all discovered sections with texture hashes
    corresponding to this slot will be commented out. If the ib section lacks an override for the slot,
    then the first discovered section with texture hash corresponding to this slot will be converted to
    a commandlist and have `this` replaced with `ps-t#`. A `run = CommandList` line will be added to the
    ib override before any drawindexed lines. The remaining sections with texture hashes corresponding
    to this slot will be commented out if they exist.
    '''

    def execute(self, default_args: DefaultArgs):
        pass



hash_commands = {
    # MARK: Anby
    '5c0240db': [(log, ('1.0: Anby Hair IB Hash',)), (add_ib_check_if_missing,)],
    '4816de84': [(log, ('1.0: Anby Body IB Hash',)), (add_ib_check_if_missing,)],
    '19df8e84': [(log, ('1.0: Anby Face IB Hash',)), (add_ib_check_if_missing,)],


    # reverted in 1.2
    # '496a781d': [
    #     (log, ('1.0: -> 1.1: Anby Hair Texcoord Hash',)),
    #     (update_hash, ('39538886',)),
    #     (log, ('+ Remapping texcoord buffer from stride 20 to 32',)),
    #     (update_buffer_element_width, (('BBBB', 'ee', 'ff', 'ee'), ('ffff', 'ee', 'ff', 'ee'), '1.1')),
    #     (log, ('+ Setting texcoord vcolor alpha to 1',)),
    #     (update_buffer_element_value, (('ffff', 'ee', 'ff', 'ee'), ('xxx1', 'xx', 'xx', 'xx'), '1.1'))
    # ],

    '39538886': [
        (log, ('1.1 -> 1.2: Anby Hair Texcoord Hash',)),
        (update_hash, ('496a781d',)),
        (log, ('+ Remapping texcoord buffer',)),
        (zzz_12_shrink_texcoord_color, ('1.2',))
    ],


    'cc114f4f': [(log, ('1.5 -> 1.6: Anby FaceA Diffuse 1024p Hash',)), (update_hash, ('692c6d2b',))],
    '2a29cb9b': [(log, ('1.5 -> 1.6: Anby FaceA Diffuse 2048p Hash',)), (update_hash, ('05d7b504',))],


    '692c6d2b': [
        (log,                           ('1.6: Anby FaceA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   (('05d7b504', '2a29cb9b'), 'Anby.FaceA.Diffuse.2048')),
    ],
    '05d7b504': [
        (log,                           ('1.6: Anby FaceA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   (('692c6d2b', 'cc114f4f'), 'Anby.FaceA.Diffuse.1024')),
    ],


    'b54f2a3d': [(log, ('1.0 -> 2.0: Anby HairA LightMap 2048p Hash',)), (update_hash, ('057f3c55',))],
    '9ceea795': [(log, ('1.0 -> 2.0: Anby HairA LightMap 1024p Hash',)), (update_hash, ('476ab69c',))],


    '6ea0023c': [
        (log,                           ('1.0: Anby HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('5c0240db', 'Anby.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7c7f96d2', 'Anby.HairA.Diffuse.1024')),
    ],
    '7c7f96d2': [
        (log,                           ('1.0: Anby HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('5c0240db', 'Anby.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6ea0023c', 'Anby.HairA.Diffuse.2048')),
    ],
    '057f3c55': [
        (log,                           ('2.0: Anby HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('5c0240db', 'Anby.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('476ab69c', '9ceea795'), 'Anby.HairA.LightMap.1024')),
    ],
    '476ab69c': [
        (log,                           ('2.0: Anby HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('5c0240db', 'Anby.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('057f3c55', 'b54f2a3d'), 'Anby.HairA.LightMap.2048')),
    ],
    '20890a00': [
        (log,                           ('1.0: Anby HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('5c0240db', 'Anby.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3101f0da', 'Anby.HairA.NormalMap.1024')),
    ],
    '3101f0da': [
        (log,                           ('1.0: Anby HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('5c0240db', 'Anby.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('20890a00', 'Anby.HairA.NormalMap.2048')),
    ],


    'b37c3b4e': [(log, ('1.5 -> 1.6: Anby BodyA Diffuse 2048p Hash',)), (update_hash, ('215ff74d',))],
    '8bd7966f': [(log, ('1.5 -> 1.6: Anby BodyA Diffuse 1024p Hash',)), (update_hash, ('8df45cb8',))],

    '7c24acc9': [(log, ('1.0 -> 2.0: Anby BodyA LightMap 2048p Hash',)), (update_hash, ('59b123c2',))],
    '9cddbf1e': [(log, ('1.0 -> 2.0: Anby BodyA LightMap 1024p Hash',)), (update_hash, ('9b57e140',))],


    '215ff74d': [
        (log,                           ('1.6: Anby BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('4816de84', 'Anby.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('8df45cb8', '8bd7966f'), 'Anby.BodyA.Diffuse.1024')),
    ],
    '8df45cb8': [
        (log,                           ('1.6: Anby BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('4816de84', 'Anby.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('215ff74d', 'b37c3b4e'), 'Anby.BodyA.Diffuse.2048')),
    ],
    '59b123c2': [
        (log,                           ('2.0: Anby BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('4816de84', 'Anby.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('9b57e140', '9cddbf1e'), 'Anby.BodyA.LightMap.1024')),
    ],
    '9b57e140': [
        (log,                           ('2.0: Anby BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('4816de84', 'Anby.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('59b123c2', '7c24acc9'), 'Anby.BodyA.LightMap.2048')),
    ],
    'ccca3b8e': [
        (log,                           ('1.0: Anby BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('4816de84', 'Anby.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1115f163', 'Anby.BodyA.MaterialMap.1024')),
    ],
    '1115f163': [
        (log,                           ('1.0: Anby BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('4816de84', 'Anby.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ccca3b8e', 'Anby.BodyA.MaterialMap.2048')),
    ],
    '19226ead': [
        (log,                           ('1.0: Anby BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('4816de84', 'Anby.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6346d69d', 'Anby.BodyA.NormalMap.1024')),
    ],
    '6346d69d': [
        (log,                           ('1.0: Anby BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('4816de84', 'Anby.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('19226ead', 'Anby.BodyA.NormalMap.2048')),
    ],



    # MARK: Anton
    '6b95c80d': [(log, ('1.0: Anton Hair IB Hash',)),   (add_ib_check_if_missing,)],
    '653fb27c': [(log, ('1.0: Anton Body IB Hash',)),   (add_ib_check_if_missing,)],
    'a21fcee4': [(log, ('1.0: Anton Jacket IB Hash',)), (add_ib_check_if_missing,)],
    'a0201907': [(log, ('1.0: Anton Face IB Hash',)),   (add_ib_check_if_missing,)],


    '15cb1aee': [
        (log,                           ('1.0: Anton FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('a0201907', 'Anton.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('842119d6', 'Anton.FaceA.Diffuse.2048')),
    ],
    '654134c1': [
        (log,                           ('1.0: Anton FaceA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('a0201907', 'Anton.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ac7fb2e2', 'Anton.FaceA.LightMap.2048')),
    ],
    '842119d6': [
        (log,                           ('1.0: Anton FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('a0201907', 'Anton.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('15cb1aee', 'Anton.FaceA.Diffuse.1024')),
    ],
    'ac7fb2e2': [
        (log,                           ('1.0: Anton FaceA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('a0201907', 'Anton.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('654134c1', 'Anton.FaceA.LightMap.1024')),
    ],


    'ee06579e': [(log, ('1.0 -> 2.0: Anton HairA LightMap 2048p Hash',)), (update_hash, ('41601dfa',))],
    '21ee9a3f': [(log, ('1.0 -> 2.0: Anton HairA LightMap 1024p Hash',)), (update_hash, ('f6e280b0',))],
    '24caeb1f': [(log, ('1.0 -> 2.0: Anton HairA MaterialMap 2048p Hash',)), (update_hash, ('d47c5823',))],
    '6fc654e1': [(log, ('1.0 -> 2.0: Anton HairA MaterialMap 1024p Hash',)), (update_hash, ('05bd454d',))],


    '571aa398': [
        (log,                           ('1.0: Anton HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('6b95c80d', 'Anton.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d4c4c604', 'Anton.HairA.Diffuse.1024')),
    ],
    'd4c4c604': [
        (log,                           ('1.0: Anton HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('6b95c80d', 'Anton.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('571aa398', 'Anton.HairA.Diffuse.2048')),
    ],
    '41601dfa': [
        (log,                           ('2.0: Anton HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('6b95c80d', 'Anton.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('f6e280b0', '21ee9a3f'), 'Anton.HairA.LightMap.1024')),
    ],
    'f6e280b0': [
        (log,                           ('2.0: Anton HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('6b95c80d', 'Anton.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('41601dfa', 'ee06579e'), 'Anton.HairA.LightMap.2048')),
    ],
    'd47c5823': [
        (log,                           ('2.0: Anton HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('6b95c80d', 'Anton.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('05bd454d', '6fc654e1'), 'Anton.HairA.MaterialMap.1024')),
    ],
    '05bd454d': [
        (log,                           ('2.0: Anton HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('6b95c80d', 'Anton.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('d47c5823', '24caeb1f'), 'Anton.HairA.MaterialMap.2048')),
    ],
    'b216f758': [
        (log,                           ('1.0: Anton HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('6b95c80d', 'Anton.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('77ae203f', 'Anton.HairA.NormalMap.1024')),
    ],
    '77ae203f': [
        (log,                           ('1.0: Anton HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('6b95c80d', 'Anton.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b216f758', 'Anton.HairA.NormalMap.2048')),
    ],


    '17cf1b74': [(log, ('1.0 -> 2.0: Anton BodyA LightMap 2048p Hash',)), (update_hash, ('ed6f4199',))],
    '8e5ba7d0': [(log, ('1.0 -> 2.0: Anton BodyA LightMap 1024p Hash',)), (update_hash, ('a937bcee',))],
    '0238b0ff': [(log, ('1.0 -> 2.0: Anton BodyA MaterialMap 2048p Hash',)), (update_hash, ('986c9716',))],
    'b7ce5f0b': [(log, ('1.0 -> 2.0: Anton BodyA MaterialMap 1024p Hash',)), (update_hash, ('bb25e0f0',))],


    '00abcf22': [
        (log,                           ('1.0: Anton BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('653fb27c', 'Anton.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('581a0958', 'Anton.BodyA.Diffuse.1024')),
    ],
    '581a0958': [
        (log,                           ('1.0: Anton BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('653fb27c', 'Anton.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('00abcf22', 'Anton.BodyA.Diffuse.2048')),
    ],
    'ed6f4199': [
        (log,                           ('2.0: Anton BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('653fb27c', 'Anton.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('a937bcee', '8e5ba7d0'), 'Anton.BodyA.LightMap.1024')),
    ],
    'a937bcee': [
        (log,                           ('2.0: Anton BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('653fb27c', 'Anton.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('ed6f4199', '17cf1b74'), 'Anton.BodyA.LightMap.2048')),
    ],
    '986c9716': [
        (log,                           ('2.0: Anton BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('653fb27c', 'Anton.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('bb25e0f0', 'b7ce5f0b'), 'Anton.BodyA.MaterialMap.1024')),
    ],
    'bb25e0f0': [
        (log,                           ('2.0: Anton BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('653fb27c', 'Anton.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('986c9716', '0238b0ff'), 'Anton.BodyA.MaterialMap.2048')),
    ],
    '1b4ad5b7': [
        (log,                           ('1.0: Anton BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('653fb27c', 'Anton.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5b2ab0e0', 'Anton.BodyA.NormalMap.1024')),
    ],
    '5b2ab0e0': [
        (log,                           ('1.0: Anton BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('653fb27c', 'Anton.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1b4ad5b7', 'Anton.BodyA.NormalMap.2048')),
    ],


    '886a664a': [(log, ('1.0 -> 2.0: Anton JacketA LightMap 2048p Hash',)), (update_hash, ('ef7880e3',))],
    'c42628a5': [(log, ('1.0 -> 2.0: Anton JacketA LightMap 1024p Hash',)), (update_hash, ('edb33cec',))],


    'd4b15508': [
        (log,                           ('1.0: Anton JacketA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('a21fcee4', 'Anton.Jacket.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f7831517', 'Anton.JacketA.Diffuse.1024')),
    ],
    'f7831517': [
        (log,                           ('1.0: Anton JacketA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('a21fcee4', 'Anton.Jacket.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d4b15508', 'Anton.JacketA.Diffuse.2048')),
    ],
    'ef7880e3': [
        (log,                           ('2.0: Anton JacketA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('a21fcee4', 'Anton.Jacket.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('edb33cec', 'c42628a5'), 'Anton.JacketA.LightMap.1024')),
    ],
    'edb33cec': [
        (log,                           ('2.0: Anton JacketA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('a21fcee4', 'Anton.Jacket.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('ef7880e3', '886a664a'), 'Anton.JacketA.LightMap.2048')),
    ],
    'd36a2f7a': [
        (log,                           ('1.0: Anton JacketA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('a21fcee4', 'Anton.Jacket.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('75bccc40', 'Anton.JacketA.MaterialMap.1024')),
    ],
    '75bccc40': [
        (log,                           ('1.0: Anton JacketA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('a21fcee4', 'Anton.Jacket.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d36a2f7a', 'Anton.JacketA.MaterialMap.2048')),
    ],
    'd7517d0e': [
        (log,                           ('1.0: Anton JacketA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('a21fcee4', 'Anton.Jacket.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ae3d5fb8', 'Anton.JacketA.NormalMap.1024')),
    ],
    'ae3d5fb8': [
        (log,                           ('1.0: Anton JacketA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('a21fcee4', 'Anton.Jacket.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d7517d0e', 'Anton.JacketA.NormalMap.2048')),
    ],



    # MARK: AstraYao
    '53cdac6c': [(log, ('1.5: AstraYao Hair IB Hash',)), (add_ib_check_if_missing,)],
    '7a110804': [(log, ('1.5: AstraYao Body IB Hash',)), (add_ib_check_if_missing,)],
    '92f33156': [(log, ('1.5: AstraYao Legs IB Hash',)), (add_ib_check_if_missing,)],
    '51831437': [(log, ('1.5: AstraYao Face IB Hash',)), (add_ib_check_if_missing,)],

    '3cd13d03': [(log, ('1.5 -> 1.6: AstraYao Body Blend Hash',)),    (update_hash, ('9d35c352',)),],
    'f8b92870': [(log, ('1.5 -> 1.6: AstraYao Hair Texcoord Hash',)), (update_hash, ('8ba0b335',)),],
    'da86a32e': [(log, ('1.5 -> 1.6: AstraYao Legs Texcoord Hash',)), (update_hash, ('1433ee78',)),],


    '3a8d0dfc': [(log, ('1.5 -> 1.6: AstraYao Face Diffuse 2048p Hash',)), (update_hash, ('c41341b2',))],
    '77670042': [(log, ('1.5 -> 1.6: AstraYao Face Diffuse 1024p Hash',)), (update_hash, ('3283b8be',))],

    'c41341b2': [
        (log,                           ('1.6: AstraYao FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('51831437', 'AstraYao.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('3283b8be', '77670042'), 'AstraYao.FaceA.Diffuse.1024')),
    ],
    '3283b8be': [
        (log,                           ('1.6: AstraYao FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('51831437', 'AstraYao.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('c41341b2', '3a8d0dfc'), 'AstraYao.FaceA.Diffuse.2048')),
    ],


    'da673df0': [(log, ('1.5A -> 1.5B: AstraYao HairA, LegsA Diffuse 2048p Hash',)),    (update_hash, ('2daa2443',))],
    '7a507e4a': [(log, ('1.5A -> 1.5B: AstraYao HairA, LegsA Diffuse 1024p Hash',)),    (update_hash, ('4b1c1b47',))],
    '34aad3b4': [(log, ('1.5A -> 1.5B: AstraYao HairA, LegsA LightMap 2048p Hash',)),   (update_hash, ('b085765e',))],
    'e4a4f975': [(log, ('1.5A -> 1.5B: AstraYao HairA, LegsA LightMap 1024p Hash',)),   (update_hash, ('c47a524a',))],

    '2daa2443': [(log, ('1.5 -> 1.6: AstraYao HairA, LegsA Diffuse 2048p Hash',)),      (update_hash, ('e634238a',))],
    '4b1c1b47': [(log, ('1.5 -> 1.6: AstraYao HairA, LegsA Diffuse 1024p Hash',)),      (update_hash, ('56c71ea2',))],
    'b085765e': [(log, ('1.5 -> 1.6: AstraYao HairA, LegsA LightMap 2048p Hash',)),     (update_hash, ('34f0706c',))],
    'c47a524a': [(log, ('1.5 -> 1.6: AstraYao HairA, LegsA LightMap 1024p Hash',)),     (update_hash, ('fd3ca2a6',))],
    'b53b2e12': [(log, ('1.5 -> 1.6: AstraYao HairA, LegsA MaterialMap 2048p Hash',)),  (update_hash, ('883a578f',))],
    '0be99d44': [(log, ('1.5 -> 1.6: AstraYao HairA, LegsA MaterialMap 1024p Hash',)),  (update_hash, ('759c15e0',))],

    'e634238a': [
        (log,                           ('1.6: AstraYao HairA, LegsA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   (('56c71ea2', '4b1c1b47', '7a507e4a'), 'AstraYao.HairA.Diffuse.1024')),
    ],
    '56c71ea2': [
        (log,                           ('1.6: AstraYao HairA, LegsA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   (('e634238a', '2daa2443', 'da673df0'), 'AstraYao.HairA.Diffuse.2048')),
    ],
    '34f0706c': [
        (log,                           ('1.6: AstraYao HairA, LegsA LightMap 2048p Hash',)),
        (multiply_section_if_missing,   (('fd3ca2a6', 'c47a524a', 'e4a4f975'), 'AstraYao.HairA.LightMap.1024')),
    ],
    'fd3ca2a6': [
        (log,                           ('1.6: AstraYao HairA, LegsA LightMap 1024p Hash',)),
        (multiply_section_if_missing,   (('34f0706c', 'b085765e', '34aad3b4'), 'AstraYao.HairA.LightMap.2048')),
    ],
    '883a578f': [
        (log,                           ('1.6: AstraYao HairA, LegsA MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   (('759c15e0', '0be99d44'), 'AstraYao.HairA.MaterialMap.1024')),
    ],
    '759c15e0': [
        (log,                           ('1.6: AstraYao HairA, LegsA MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   (('883a578f', 'b53b2e12'), 'AstraYao.HairA.MaterialMap.2048')),
    ],


    'd7f1c157': [
        (log,                           ('1.5: AstraYao BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('7a110804', 'AstraYao.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e523eb0f', 'AstraYao.BodyA.Diffuse.1024')),
    ],
    'e523eb0f': [
        (log,                           ('1.5: AstraYao BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('7a110804', 'AstraYao.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d7f1c157', 'AstraYao.BodyA.Diffuse.2048')),
    ],
    'dba7d767': [
        (log,                           ('1.5: AstraYao BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('7a110804', 'AstraYao.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3f9f0d8a', 'AstraYao.BodyA.LightMap.1024')),
    ],
    '3f9f0d8a': [
        (log,                           ('1.5: AstraYao BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('7a110804', 'AstraYao.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('dba7d767', 'AstraYao.BodyA.LightMap.2048')),
    ],
    '21d5f5e3': [
        (log,                           ('1.5: AstraYao BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('7a110804', 'AstraYao.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c4248e2d', 'AstraYao.BodyA.MaterialMap.1024')),
    ],
    'c4248e2d': [
        (log,                           ('1.5: AstraYao BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('7a110804', 'AstraYao.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('21d5f5e3', 'AstraYao.BodyA.MaterialMap.2048')),
    ],



    # MARK: AstraSkin
    '02d8a2cb': [(log, ('1.5: AstraSkin Body IB Hash',)), (add_ib_check_if_missing,)],

    '56abc3a3': [(log, ('1.5 -> 1.6: AstraSkin BodyA MaterialMap 2048p Hash',)),   (update_hash, ('43a4d256',))],
    '6989dc5a': [(log, ('1.5 -> 1.6: AstraSkin BodyA MaterialMap 1024p Hash',)),   (update_hash, ('6da1b76a',))],

    '7ce9f1db': [(log, ('1.5 -> 2.0: AstraSkin BodyA LightMap 2048p Hash',)),      (update_hash, ('515f9beb',))],
    '83ede428': [(log, ('1.5 -> 2.0: AstraSkin BodyA LightMap 1024p Hash',)),      (update_hash, ('cf8ecb3b',))],
    '43a4d256': [(log, ('1.6 -> 2.0: AstraSkin BodyA MaterialMap 2048p Hash',)),   (update_hash, ('fa2f509f',))],
    '6da1b76a': [(log, ('1.6 -> 2.0: AstraSkin BodyA MaterialMap 1024p Hash',)),   (update_hash, ('03df0be9',))],

    '7301ca3a': [
        (log,                           ('1.5: AstraSkin BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('02d8a2cb', 'AstraSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8212713f', 'AstraSkin.BodyA.Diffuse.1024')),
    ],
    '8212713f': [
        (log,                           ('1.5: AstraSkin BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('02d8a2cb', 'AstraSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7301ca3a', 'AstraSkin.BodyA.Diffuse.2048')),
    ],
    '515f9beb': [
        (log,                           ('2.0: AstraSkin BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('02d8a2cb', 'AstraSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('cf8ecb3b', '83ede428'), 'AstraSkin.BodyA.LightMap.1024')),
    ],
    'cf8ecb3b': [
        (log,                           ('2.0: AstraSkin BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('02d8a2cb', 'AstraSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('515f9beb', '7ce9f1db'), 'AstraSkin.BodyA.LightMap.2048')),
    ],
    'fa2f509f': [
        (log,                           ('2.0: AstraSkin BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('02d8a2cb', 'AstraSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('03df0be9', '6da1b76a', '6989dc5a'), 'AstraSkin.BodyA.MaterialMap.1024')),
    ],
    '03df0be9': [
        (log,                           ('2.0: AstraSkin BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('02d8a2cb', 'AstraSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('fa2f509f', '43a4d256', '56abc3a3'), 'AstraSkin.BodyA.MaterialMap.2048')),
    ],



    # MARK: Belle
    'bea4a483': [(log, ('1.0: Belle Hair IB Hash',)), (add_ib_check_if_missing,)],
    '1817f3ca': [(log, ('1.0: Belle Body IB Hash',)), (add_ib_check_if_missing,)],
    '9a9780a7': [(log, ('1.0: Belle Face IB Hash',)), (add_ib_check_if_missing,)],

    'caf95576': [
        (log,                         ('1.0 -> 1.1: Belle Body Texcoord Hash',)),
        (update_hash,                 ('801edbf4',)),
        (log,                         ('1.0 -> 1.1: Belle Body Blend Remap',)),
        (update_buffer_blend_indices, (
            'd2844c01',
            (3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 61, 62, 63, 64, 65, 66, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 126, 127),
            (6, 7, 3, 5, 4, 18, 9, 10, 11, 12, 13, 14, 15, 16, 17, 21, 25, 24, 20, 22, 23, 38, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 47, 48, 53, 56, 45, 46, 49, 50, 51, 52, 54, 55, 60, 61, 66, 58, 59, 62, 63, 64, 65, 104, 95, 96, 97, 98, 99, 100, 101, 102, 103, 127, 126),
        ))
    ],

    '77eef7e8': [
        (log,                           ('1.0: Belle FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('9a9780a7', 'Belle.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('75ec3614', 'Belle.FaceA.Diffuse.2048')),
    ],
    '75ec3614': [
        (log,                           ('1.0: Belle FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('9a9780a7', 'Belle.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('77eef7e8', 'Belle.FaceA.Diffuse.1024')),
    ],


    '24c47ca5': [(log, ('1.4 -> 1.5: Belle HairA MaterialMap 2048p Hash',)), (update_hash, ('34bdb036',))],
    '4b6ef993': [(log, ('1.4 -> 1.5: Belle HairA MaterialMap 1024p Hash',)), (update_hash, ('7542ef4b',))],

    'f1ee2105': [(log, ('1.0 -> 2.0: Belle HairA LightMap 2048p Hash',)), (update_hash, ('7d562f53',))],
    '2e656f2f': [(log, ('1.0 -> 2.0: Belle HairA LightMap 1024p Hash',)), (update_hash, ('f44f330b',))],


    '1ce58567': [
        (log,                           ('1.0: Belle HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('bea4a483', 'Belle.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('08f04d95', 'Belle.HairA.Diffuse.1024')),
    ],
    '08f04d95': [
        (log,                           ('1.0: Belle HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('bea4a483', 'Belle.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1ce58567', 'Belle.HairA.Diffuse.2048')),
    ],
    '7d562f53': [
        (log,                           ('2.0: Belle HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('bea4a483', 'Belle.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('f44f330b', '2e656f2f'), 'Belle.HairA.LightMap.1024')),
    ],
    'f44f330b': [
        (log,                           ('2.0: Belle HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('bea4a483', 'Belle.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('7d562f53', 'f1ee2105'), 'Belle.HairA.LightMap.2048')),
    ],
    '34bdb036': [
        (log,                           ('1.5: Belle HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('bea4a483', 'Belle.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('7542ef4b', '4b6ef993'), 'Belle.HairA.MaterialMap.1024')),
    ],
    '7542ef4b': [
        (log,                           ('1.5: Belle HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('bea4a483', 'Belle.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('34bdb036', '24c47ca5'), 'Belle.HairA.MaterialMap.2048')),
    ],
    '89b147ff': [
        (log,                           ('1.0: Belle HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('bea4a483', 'Belle.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6b55c039', 'Belle.HairA.NormalMap.1024')),
    ],
    '6b55c039': [
        (log,                           ('1.0: Belle HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('bea4a483', 'Belle.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('89b147ff', 'Belle.HairA.NormalMap.2048')),
    ],


    'd2960560': [(log, ('1.4 -> 1.5: Belle BodyA Diffuse 2048p Hash',)), (update_hash, ('24639b77',))],
    '4454fb58': [(log, ('1.4 -> 1.5: Belle BodyA Diffuse 1024p Hash',)), (update_hash, ('b9c7f71b',))],
    'bf286c84': [(log, ('1.4 -> 1.5: Belle BodyA LightMap 2048p Hash',)), (update_hash, ('7947679c',))],
    '2ed82c57': [(log, ('1.4 -> 1.5: Belle BodyA LightMap 1024p Hash',)), (update_hash, ('a4d3687d',))],


    '24639b77': [
        (log,                           ('1.5: Belle BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('1817f3ca', 'Belle.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('b9c7f71b', '4454fb58'), 'Belle.BodyA.Diffuse.1024')),
    ],
    'b9c7f71b': [
        (log,                           ('1.5: Belle BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('1817f3ca', 'Belle.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('24639b77', 'd2960560'), 'Belle.BodyA.Diffuse.2048')),
    ],
    '7947679c': [
        (log,                           ('1.5: Belle BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('1817f3ca', 'Belle.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('a4d3687d', '2ed82c57'), 'Belle.BodyA.LightMap.1024')),
    ],
    'a4d3687d': [
        (log,                           ('1.5: Belle BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('1817f3ca', 'Belle.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('7947679c', 'bf286c84'), 'Belle.BodyA.LightMap.2048')),
    ],
    '33f28c6d': [
        (log,                           ('1.0: Belle BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('1817f3ca', 'Belle.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b1abe877', 'Belle.BodyA.MaterialMap.1024')),
    ],
    'b1abe877': [
        (log,                           ('1.0: Belle BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('1817f3ca', 'Belle.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('33f28c6d', 'Belle.BodyA.MaterialMap.2048')),
    ],
    'f04f7ab9': [
        (log,                           ('1.0: Belle BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('1817f3ca', 'Belle.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c0bd8516', 'Belle.BodyA.NormalMap.1024')),
    ],
    'c0bd8516': [
        (log,                           ('1.0: Belle BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('1817f3ca', 'Belle.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f04f7ab9', 'Belle.BodyA.NormalMap.2048')),
    ],



    # MARK: BelleSkin
    'aa9ffb85': [(log, ('2.0: BelleSkin Hair IB Hash',)), (add_ib_check_if_missing,)],    
    '860e1558': [(log, ('2.0: BelleSkin Body IB Hash',)), (add_ib_check_if_missing,)],
    'bcc9e4e1': [(log, ('2.0: BelleSkin Stock IB Hash',)), (add_ib_check_if_missing,)],


    'cac9fd5d': [
        (log,                           ('2.0: BelleSkin BodyA StockA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('860e1558', 'BelleSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('59218fac', 'BelleSkin.BodyA.Diffuse.1024')),
    ],
    '59218fac': [
        (log,                           ('2.0: BelleSkin BodyA StockA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('860e1558', 'BelleSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('cac9fd5d', 'BelleSkin.BodyA.Diffuse.2048')),
    ],
    '74f2fae3': [
        (log,                           ('2.0: BelleSkin BodyA StockA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('860e1558', 'BelleSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('93d94f22', 'BelleSkin.BodyA.LightMap.1024')),
    ],
    '93d94f22': [
        (log,                           ('2.0: BelleSkin BodyA StockA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('860e1558', 'BelleSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('74f2fae3', 'BelleSkin.BodyA.LightMap.2048')),
    ],
    '657402d0': [
        (log,                           ('2.0: BelleSkin BodyA StockA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('860e1558', 'BelleSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b95c08fb', 'BelleSkin.BodyA.MaterialMap.1024')),
    ],
    'b95c08fb': [
        (log,                           ('2.0: BelleSkin BodyA StockA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('860e1558', 'BelleSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('657402d0', 'BelleSkin.BodyA.MaterialMap.2048')),
    ],



    # MARK: Ben
    '9c4f1a9a': [(log, ('1.0: Ben Hair IB Hash',)), (add_ib_check_if_missing,)],
    '94288cca': [(log, ('1.0: Ben Body IB Hash',)), (add_ib_check_if_missing,)],

    'a2f79d33': [(log, ('1.0 -> 2.0: Ben Body Blend Hash',)),    (update_hash, ('21dd67a7',)),],


    'cc195dc5': [(log, ('1.0 -> 2.0: Ben HairA LightMap 2048p Hash',)),       (update_hash, ('2fa5ffa7',))],
    '1439d2b9': [(log, ('1.0 -> 2.0: Ben HairA LightMap 1024p Hash',)),       (update_hash, ('9372e123',))],
    '0bbceea0': [(log, ('1.0 -> 2.0: Ben HairA MaterialMap 2048p Hash',)),    (update_hash, ('12e5120e',))],
    'd665246d': [(log, ('1.0 -> 2.0: Ben HairA MaterialMap 1024p Hash',)),    (update_hash, ('dd8c0b3a',))],


    '00002f2c': [
        (log,                           ('1.0: Ben HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('9c4f1a9a', 'Ben.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8d83daba', 'Ben.HairA.Diffuse.1024')),
    ],
    '8d83daba': [
        (log,                           ('1.0: Ben HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('9c4f1a9a', 'Ben.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('00002f2c', 'Ben.HairA.Diffuse.2048')),
    ],
    '2fa5ffa7': [
        (log,                           ('2.0: Ben HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('9c4f1a9a', 'Ben.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('9372e123', '1439d2b9'), 'Ben.HairA.LightMap.1024')),
    ],
    '9372e123': [
        (log,                           ('2.0: Ben HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('9c4f1a9a', 'Ben.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('2fa5ffa7', 'cc195dc5'), 'Ben.HairA.LightMap.2048')),
    ],
    '12e5120e': [
        (log,                           ('2.0: Ben HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('9c4f1a9a', 'Ben.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('dd8c0b3a', 'd665246d'), 'Ben.HairA.MaterialMap.1024')),
    ],
    'dd8c0b3a': [
        (log,                           ('2.0: Ben HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('9c4f1a9a', 'Ben.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('12e5120e', '0bbceea0'), 'Ben.HairA.MaterialMap.2048')),
    ],
    '894ea737': [
        (log,                           ('1.0: Ben HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('9c4f1a9a', 'Ben.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ba809960', 'Ben.HairA.NormalMap.1024')),
    ],
    'ba809960': [
        (log,                           ('1.0: Ben HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('9c4f1a9a', 'Ben.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('894ea737', 'Ben.HairA.NormalMap.2048')),
    ],


    'cb84ed5e': [(log, ('1.0 -> 2.0: Ben BodyA LightMap 2048p Hash',)),     (update_hash, ('d27a8f6b',))],
    '6a80c2d8': [(log, ('1.0 -> 2.0: Ben BodyA LightMap 1024p Hash',)),     (update_hash, ('9a724295',))],
    '3f4f6bc0': [(log, ('1.0 -> 2.0: Ben BodyA MaterialMap 2048p Hash',)),  (update_hash, ('2edd6f62',))],
    'decc28c5': [(log, ('1.0 -> 2.0: Ben BodyA MaterialMap 1024p Hash',)),  (update_hash, ('3678fad4',))],


    '0313ed95': [
        (log,                           ('1.0: Ben BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('94288cca', 'Ben.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d8dc4645', 'Ben.BodyA.Diffuse.1024')),
    ],
    'd8dc4645': [
        (log,                           ('1.0: Ben BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('94288cca', 'Ben.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0313ed95', 'Ben.BodyA.Diffuse.2048')),
    ],
    'd27a8f6b': [
        (log,                           ('2.0: Ben BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('94288cca', 'Ben.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('9a724295', '6a80c2d8'), 'Ben.BodyA.LightMap.1024')),
    ],
    '9a724295': [
        (log,                           ('2.0: Ben BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('94288cca', 'Ben.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('d27a8f6b', 'cb84ed5e'), 'Ben.BodyA.LightMap.2048')),
    ],
    '2edd6f62': [
        (log,                           ('2.0: Ben BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('94288cca', 'Ben.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('3678fad4', 'decc28c5'), 'Ben.BodyA.MaterialMap.1024')),
    ],
    '3678fad4': [
        (log,                           ('2.0: Ben BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('94288cca', 'Ben.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('2edd6f62', '3f4f6bc0'), 'Ben.BodyA.MaterialMap.2048')),
    ],
    '1b79fa5c': [
        (log,                           ('1.0: Ben BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('94288cca', 'Ben.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f6ecc618', 'Ben.BodyA.NormalMap.1024')),
    ],
    'f6ecc618': [
        (log,                           ('1.0: Ben BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('94288cca', 'Ben.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1b79fa5c', 'Ben.BodyA.NormalMap.2048')),
    ],



    # MARK: Billy
    '21e98aeb': [(log, ('1.0: Billy Hair IB Hash',)), (add_ib_check_if_missing,)],
    '3371580a': [(log, ('1.0: Billy Body IB Hash',)), (add_ib_check_if_missing,)],
    'dc7978f3': [(log, ('1.0: Billy Face IB Hash',)), (add_ib_check_if_missing,)],


    '9f02ef2b': [(log, ('1.0 -> 2.0: Billy FaceA LightMap 2048p Hash',)),       (update_hash, ('cf4769ce',))],
    '877e1a0d': [(log, ('1.0 -> 2.0: Billy FaceA LightMap 1024p Hash',)),       (update_hash, ('f5a507da',))],
    'd166c3e5': [(log, ('1.0 -> 2.0: Billy FaceA MaterialMap 2048p Hash',)),    (update_hash, ('3a7d88a1',))],
    'dc2f2dd2': [(log, ('1.0 -> 2.0: Billy FaceA MaterialMap 1024p Hash',)),    (update_hash, ('e534abc0',))],


    '6f8a9cdb': [
        (log,                           ('1.0: Billy FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('dc7978f3', 'Billy.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a1d68c9e', 'Billy.FaceA.Diffuse.1024')),
    ],
    'a1d68c9e': [
        (log,                           ('1.0: Billy FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('dc7978f3', 'Billy.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6f8a9cdb', 'Billy.FaceA.Diffuse.2048')),
    ],
    'cf4769ce': [
        (log,                           ('2.0: Billy FaceA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('dc7978f3', 'Billy.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('f5a507da', '877e1a0d'), 'Billy.FaceA.LightMap.1024')),
    ],
    'f5a507da': [
        (log,                           ('2.0: Billy FaceA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('dc7978f3', 'Billy.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('cf4769ce', '9f02ef2b'), 'Billy.FaceA.LightMap.2048')),
    ],
    '3a7d88a1': [
        (log,                           ('2.0: Billy FaceA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('dc7978f3', 'Billy.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('e534abc0', 'dc2f2dd2'), 'Billy.FaceA.MaterialMap.1024')),
    ],
    'e534abc0': [
        (log,                           ('2.0: Billy FaceA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('dc7978f3', 'Billy.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('3a7d88a1', 'd166c3e5'), 'Billy.FaceA.MaterialMap.2048')),
    ],
    'e5f2fc35': [
        (log,                           ('1.0: Billy FaceA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('dc7978f3', 'Billy.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('eed0cd5f', 'Billy.FaceA.NormalMap.1024')),
    ],
    'eed0cd5f': [
        (log,                           ('1.0: Billy FaceA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('dc7978f3', 'Billy.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e5f2fc35', 'Billy.FaceA.NormalMap.2048')),
    ],


    '0475db07': [(log, ('1.0 -> 2.0: Billy HairA Diffuse 2048p Hash',)),          (update_hash, ('ff939fb7',))],
    'c0360c81': [(log, ('1.0 -> 2.0: Billy HairA Diffuse 1024p Hash',)),          (update_hash, ('6a6a1c79',))],

    '4817b1bc': [(log, ('1.0 -> 2.0: Billy HairA LightMap 2048p Hash',)),         (update_hash, ('b6e1da4b',))],
    'd269a0a1': [(log, ('1.0 -> 1.x: Billy HairA LightMap 1024p Hash',)),         (update_hash, ('f6749665',))],
    'f6749665': [(log, ('1.x -> 2.0: Billy HairA LightMap 1024p Hash',)),         (update_hash, ('2edbc842',))],


    'ff939fb7': [
        (log,                           ('2.0: Billy HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('21e98aeb', 'Billy.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('6a6a1c79', 'c0360c81'), 'Billy.HairA.Diffuse.1024')),
    ],
    '6a6a1c79': [
        (log,                           ('2.0: Billy HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('21e98aeb', 'Billy.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('ff939fb7', '0475db07'), 'Billy.HairA.Diffuse.2048')),
    ],
    'b6e1da4b': [
        (log,                           ('2.0: Billy HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('21e98aeb', 'Billy.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('2edbc842', 'f6749665', 'd269a0a1'), 'Billy.HairA.LightMap.1024')),
    ],
    '2edbc842': [
        (log,                           ('2.0: Billy HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('21e98aeb', 'Billy.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('b6e1da4b', '4817b1bc'), 'Billy.HairA.LightMap.2048')),
    ],
    '47bbe297': [
        (log,                           ('1.0: Billy HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('21e98aeb', 'Billy.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('27185819', 'Billy.HairA.NormalMap.1024')),
    ],
    '27185819': [
        (log,                           ('1.0: Billy HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('21e98aeb', 'Billy.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('47bbe297', 'Billy.HairA.NormalMap.2048')),
    ],


    '789b054e': [(log, ('1.0 -> 2.0: Billy BodyA LightMap 2048p Hash',)),       (update_hash, ('6305a7f4',))],
    '0d5d374f': [(log, ('1.0 -> 2.0: Billy BodyA LightMap 1024p Hash',)),       (update_hash, ('adc2ec7c',))],


    '399d9865': [
        (log,                           ('1.0: Billy BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('3371580a', 'Billy.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('af07a583', 'Billy.BodyA.Diffuse.1024')),
    ],
    'af07a583': [
        (log,                           ('1.0: Billy BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('3371580a', 'Billy.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('399d9865', 'Billy.BodyA.Diffuse.2048')),
    ],
    '6305a7f4': [
        (log,                           ('2.0: Billy BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('3371580a', 'Billy.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('adc2ec7c', '0d5d374f'), 'Billy.BodyA.LightMap.1024')),
    ],
    'adc2ec7c': [
        (log,                           ('2.0: Billy BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('3371580a', 'Billy.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('6305a7f4', '789b054e'), 'Billy.BodyA.LightMap.2048')),
    ],
    '9cb20fa9': [
        (log,                           ('1.0: Billy BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('3371580a', 'Billy.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b3cabf65', 'Billy.BodyA.MaterialMap.1024')),
    ],
    'b3cabf65': [
        (log,                           ('1.0: Billy BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('3371580a', 'Billy.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9cb20fa9', 'Billy.BodyA.MaterialMap.2048')),
    ],
    '56b5953e': [
        (log,                           ('1.0: Billy BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('3371580a', 'Billy.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('71d95d5d', 'Billy.BodyA.NormalMap.1024')),
    ],
    '71d95d5d': [
        (log,                           ('1.0: Billy BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('3371580a', 'Billy.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('56b5953e', 'Billy.BodyA.NormalMap.2048')),
    ],


    # MARK: Burnice
    'f779fb81': [(log, ('1.2: Burnice Hair IB Hash',)), (add_ib_check_if_missing,)],
    'af63e974': [(log, ('1.2: Burnice Body IB Hash',)), (add_ib_check_if_missing,)],
    'b3f6fcb3': [(log, ('1.2: Burnice Face IB Hash',)), (add_ib_check_if_missing,)],

    'c9c87bb1': [(log, ('1.3 -> 1.4: Burnice FaceA Diffuse 1024p Hash',)), (update_hash, ('68f0fb19',)),],
    '68f0fb19': [
        (log,                           ('1.4: Burnice FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('b3f6fcb3', 'Burnice.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('c4b6bb10', 'e338bb82'), 'Burnice.FaceA.Diffuse.2048')),
    ],
    'e338bb82': [(log, ('1.3 -> 1.4: Burnice FaceA Diffuse 2048p Hash',)), (update_hash, ('c4b6bb10',)),],
    'c4b6bb10': [
        (log,                           ('1.4: Burnice FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('b3f6fcb3', 'Burnice.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('68f0fb19', 'c9c87bb1'), 'Burnice.FaceA.Diffuse.1024')),
    ],

    '609b50a9': [
        (log,                           ('1.2: Burnice HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('f779fb81', 'Burnice.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4568c6b3', 'Burnice.HairA.Diffuse.1024')),
    ],
    '4568c6b3': [
        (log,                           ('1.2: Burnice HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('f779fb81', 'Burnice.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('609b50a9', 'Burnice.HairA.Diffuse.2048')),
    ],
    'bf0042b9': [
        (log,                           ('1.2: Burnice HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('f779fb81', 'Burnice.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('08770e8c', 'Burnice.HairA.LightMap.1024')),
    ],
    '08770e8c': [
        (log,                           ('1.2: Burnice HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('f779fb81', 'Burnice.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('bf0042b9', 'Burnice.HairA.LightMap.2048')),
    ],
    '5f2840f1': [
        (log,                           ('1.2: Burnice HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('f779fb81', 'Burnice.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3ae3ea20', 'Burnice.HairA.MaterialMap.1024')),
    ],
    '3ae3ea20': [
        (log,                           ('1.2: Burnice HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('f779fb81', 'Burnice.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5f2840f1', 'Burnice.HairA.MaterialMap.2048')),
    ],
    '438cf629': [
        (log,                           ('1.2: Burnice HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('f779fb81', 'Burnice.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0050e0d2', 'Burnice.HairA.NormalMap.1024')),
    ],
    '0050e0d2': [
        (log,                           ('1.2: Burnice HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('f779fb81', 'Burnice.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('438cf629', 'Burnice.HairA.NormalMap.2048')),
    ],

    '50bf6521': [
        (log,                           ('1.2: Burnice BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('af63e974', 'Burnice.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f0e67001', 'Burnice.BodyA.Diffuse.1024')),
    ],
    'f0e67001': [
        (log,                           ('1.2: Burnice BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('af63e974', 'Burnice.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('50bf6521', 'Burnice.BodyA.Diffuse.2048')),
    ],
    'f4e05ee7': [
        (log,                           ('1.2: Burnice BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('af63e974', 'Burnice.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0a3ba8ac', 'Burnice.BodyA.LightMap.1024')),
    ],
    '0a3ba8ac': [
        (log,                           ('1.2: Burnice BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('af63e974', 'Burnice.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f4e05ee7', 'Burnice.BodyA.LightMap.2048')),
    ],
    'c321481d': [
        (log,                           ('1.2: Burnice BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('af63e974', 'Burnice.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e37e7622', 'Burnice.BodyA.MaterialMap.1024')),
    ],
    'e37e7622': [
        (log,                           ('1.2: Burnice BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('af63e974', 'Burnice.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c321481d', 'Burnice.BodyA.MaterialMap.2048')),
    ],
    '0f2c69e2': [
        (log,                           ('1.2: Burnice BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('af63e974', 'Burnice.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0c4f338a', 'Burnice.BodyA.NormalMap.1024')),
    ],
    '0c4f338a': [
        (log,                           ('1.2: Burnice BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('af63e974', 'Burnice.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0f2c69e2', 'Burnice.BodyA.NormalMap.2048')),
    ],



    # MARK: Caesar
    '7a8fa826': [(log, ('1.2: Caesar Hair IB Hash',)), (add_ib_check_if_missing,)],
    '92061e5e': [(log, ('1.2: Caesar Body IB Hash',)), (add_ib_check_if_missing,)],
    '6caaeb53': [(log, ('1.2: Caesar Face IB Hash',)), (add_ib_check_if_missing,)],

    'af291513': [
        (log,            ('1.2 -> 1.3: Caesar Hair Texcoord Hash',)),
        (update_hash,    ('72537fa3',)),
        (log,            ('+ Remapping texcoord buffer',)),
        (zzz_13_remap_texcoord, (
            '13_Caesar_hair',
            ('4B','2e','2f','2e'),
            ('4B','2f','2f','2f')
        )),
    ],
    '3b2a70a5': [
        (log,            ('1.2 -> 1.3: Caesar Body Texcoord Hash',)),
        (update_hash,    ('0ca81129',)),
        (log,            ('+ Remapping texcoord buffer',)),
        (zzz_13_remap_texcoord, (
            '13_Caesar_body',
            ('4B','2e','2f','2e', '2e'),
            ('4B','2f','2f','2f', '2f')
        )),
    ],


    '84d53514': [
        (log,                           ('1.2: Caesar FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('6caaeb53', 'Caesar.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('13098244', 'Caesar.FaceA.Diffuse.2048')),
    ],
    '13098244': [
        (log,                           ('1.2: Caesar FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('6caaeb53', 'Caesar.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('84d53514', 'Caesar.FaceA.Diffuse.1024')),
    ],


    'bf19954f': [(log, ('1.2 -> 2.0: Caesar HairA LightMap 2048p Hash',)),           (update_hash, ('d5d3585b',))],
    'c7115c4b': [(log, ('1.2 -> 2.0: Caesar HairA LightMap 1024p Hash',)),           (update_hash, ('89b2d3b3',))],


    '9ce3e80c': [
        (log,                           ('1.2: Caesar HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('7a8fa826', 'Caesar.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b004ab49', 'Caesar.HairA.Diffuse.1024')),
    ],
    'b004ab49': [
        (log,                           ('1.2: Caesar HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('7a8fa826', 'Caesar.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9ce3e80c', 'Caesar.HairA.Diffuse.2048')),
    ],
    'd5d3585b': [
        (log,                           ('2.0: Caesar HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('7a8fa826', 'Caesar.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('89b2d3b3', 'c7115c4b'), 'Caesar.HairA.LightMap.1024')),
    ],
    '89b2d3b3': [
        (log,                           ('2.0: Caesar HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('7a8fa826', 'Caesar.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('d5d3585b', 'bf19954f'), 'Caesar.HairA.LightMap.2048')),
    ],
    '350b827e': [
        (log,                           ('1.2: Caesar HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('7a8fa826', 'Caesar.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2204f89a', 'Caesar.HairA.MaterialMap.1024')),
    ],
    '2204f89a': [
        (log,                           ('1.2: Caesar HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('7a8fa826', 'Caesar.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('350b827e', 'Caesar.HairA.MaterialMap.2048')),
    ],
    '10af3807': [
        (log,                           ('1.2: Caesar HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('7a8fa826', 'Caesar.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e17b3529', 'Caesar.HairA.NormalMap.1024')),
    ],
    'e17b3529': [
        (log,                           ('1.2: Caesar HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('7a8fa826', 'Caesar.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('10af3807', 'Caesar.HairA.NormalMap.2048')),
    ],


    'c1f1e12f': [(log, ('1.3 -> 1.4: Caesar BodyA NormalMap 2048p Hash',)),     (update_hash, ('36f39b49',)),],
    'f1c6c309': [(log, ('1.4B -> 1.4C: Caesar BodyA NormalMap 2048p Hash',)),   (update_hash, ('36f39b49',)),],
    '8cdf95d0': [(log, ('1.3 -> 1.4: Caesar BodyA NormalMap 1024p Hash',)),     (update_hash, ('a8abff9d',)),],


    '5e2cea1a': [
        (log,                           ('1.2: Caesar BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('92061e5e', 'Caesar.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f4b78da0', 'Caesar.BodyA.Diffuse.1024')),
    ],
    'f4b78da0': [
        (log,                           ('1.2: Caesar BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('92061e5e', 'Caesar.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5e2cea1a', 'Caesar.BodyA.Diffuse.2048')),
    ],
    '6296d481': [
        (log,                           ('1.2: Caesar BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('92061e5e', 'Caesar.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a9e24ba0', 'Caesar.BodyA.LightMap.1024')),
    ],
    'a9e24ba0': [
        (log,                           ('1.2: Caesar BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('92061e5e', 'Caesar.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6296d481', 'Caesar.BodyA.LightMap.2048')),
    ],
    'd5d89d5b': [
        (log,                           ('1.2: Caesar BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('92061e5e', 'Caesar.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('328bc108', 'Caesar.BodyA.MaterialMap.1024')),
    ],
    '328bc108': [
        (log,                           ('1.2: Caesar BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('92061e5e', 'Caesar.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d5d89d5b', 'Caesar.BodyA.MaterialMap.2048')),
    ],
    '36f39b49': [
        (log,                           ('1.4: Caesar BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('92061e5e', 'Caesar.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('a8abff9d', '8cdf95d0'), 'Caesar.BodyA.NormalMap.1024')),
    ],
    'a8abff9d': [
        (log,                           ('1.4: Caesar BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('92061e5e', 'Caesar.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('36f39b49', 'f1c6c309', 'c1f1e12f'), 'Caesar.BodyA.NormalMap.2048')),
    ],



    # MARK: Corin
    '5a839fb2': [(log, ('1.0: Corin Hair IB Hash',)), (add_ib_check_if_missing,)],
    'e74620b5': [(log, ('1.0: Corin Body IB Hash',)), (add_ib_check_if_missing,)],
    '5f803336': [(log, ('1.0: Corin Bear IB Hash',)), (add_ib_check_if_missing,)],
    'a0c80593': [(log, ('1.0: Corin Face IB Hash',)), (add_ib_check_if_missing,)],


    '8d999156': [(log, ('1.3 -> 1.4: Corin Hair Blend Hash',)),    (update_hash, ('5fa50113',)),],
    '2cf242f4': [(log, ('1.3 -> 1.4: Corin Hair Texcoord Hash',)), (update_hash, ('abc95b03',)),],


    '97022d3c': [
        (log,                           ('1.0: Corin FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('a0c80593', 'Corin.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6d662824', 'Corin.FaceA.Diffuse.2048')),
    ],
    '6d662824': [
        (log,                           ('1.0: Corin FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('a0c80593', 'Corin.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('97022d3c', 'Corin.FaceA.Diffuse.1024')),
    ],


    '929aca42': [(log, ('1.0 -> 2.0: Corin HairA LightMap 2048p Hash',)),           (update_hash, ('74d66671',))],
    'edff2372': [(log, ('1.0 -> 2.0: Corin HairA LightMap 1024p Hash',)),           (update_hash, ('0f300531',))],


    '60526444': [
        (log,                           ('1.0: Corin HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('5a839fb2', 'Corin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('651e96f8', 'Corin.HairA.Diffuse.1024')),
    ],
    '651e96f8': [
        (log,                           ('1.0: Corin HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('5a839fb2', 'Corin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('60526444', 'Corin.HairA.Diffuse.2048')),
    ],
    '74d66671': [
        (log,                           ('2.0: Corin HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('5a839fb2', 'Corin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('0f300531', 'edff2372'), 'Corin.HairA.LightMap.1024')),
    ],
    '0f300531': [
        (log,                           ('2.0: Corin HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('5a839fb2', 'Corin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('74d66671', '929aca42'), 'Corin.HairA.LightMap.2048')),
    ],
    # '23b4c60d': [
    #     (log,                           ('1.0: Corin HairA MaterialMap 2048p Hash',)),
    #     (add_section_if_missing,        ('5a839fb2', 'Corin.Hair.IB', 'match_priority = 0\n')),
    #     (multiply_section_if_missing,   ('1b88e01e', 'Corin.HairA.MaterialMap.1024')),
    # ],
    # '1b88e01e': [
    #     (log,                           ('1.0: Corin HairA MaterialMap 1024p Hash',)),
    #     (add_section_if_missing,        ('5a839fb2', 'Corin.Hair.IB', 'match_priority = 0\n')),
    #     (multiply_section_if_missing,   ('23b4c60d', 'Corin.HairA.MaterialMap.2048')),
    # ],
    '4a68ef99': [
        (log,                           ('1.0: Corin HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('5a839fb2', 'Corin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ab8956c8', 'Corin.HairA.NormalMap.1024')),
    ],
    'ab8956c8': [
        (log,                           ('1.0: Corin HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('5a839fb2', 'Corin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4a68ef99', 'Corin.HairA.NormalMap.2048')),
    ],


    '75e05cdc': [(log, ('1.0 -> 2.0: Corin BodyA, BearA LightMap 2048p Hash',)),            (update_hash, ('e1c1718f',))],
    'af7eda82': [(log, ('1.0 -> 2.0: Corin BodyA, BearA LightMap 1024p Hash',)),            (update_hash, ('068be251',))],
    '50a0faea': [(log, ('1.0 -> 2.0: Corin BodyA, BearA MaterialMap 2048p Hash',)),         (update_hash, ('e58d9767',))],
    '9dc9c0f6': [(log, ('1.0 -> 2.0: Corin BodyA, BearA MaterialMap 1024p Hash',)),         (update_hash, ('50ed6c50',))],


    'af9d845a': [
        (log,                           ('1.0: Corin BodyA, BearA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   ('681f5162', 'Corin.BodyA.Diffuse.1024')),
    ],
    '681f5162': [
        (log,                           ('1.0: Corin BodyA, BearA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   ('af9d845a', 'Corin.BodyA.Diffuse.2048')),
    ],
    'e1c1718f': [
        (log,                           ('2.0: Corin BodyA, BearA LightMap 2048p Hash',)),
        (multiply_section_if_missing,   (('068be251', 'af7eda82'), 'Corin.BodyA.LightMap.1024')),
    ],
    '068be251': [
        (log,                           ('2.0: Corin BodyA, BearA LightMap 1024p Hash',)),
        (multiply_section_if_missing,   (('e1c1718f', '75e05cdc'), 'Corin.BodyA.LightMap.2048')),
    ],
    'e58d9767': [
        (log,                           ('2.0: Corin BodyA, BearA MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   (('50ed6c50', '9dc9c0f6'), 'Corin.BodyA.MaterialMap.1024')),
    ],
    '50ed6c50': [
        (log,                           ('2.0: Corin BodyA, BearA MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   (('e58d9767', '50a0faea'), 'Corin.BodyA.MaterialMap.2048')),
    ],
    '289f4c58': [
        (log,                           ('1.0: Corin BodyA, BearA NormalMap 2048p Hash',)),
        (multiply_section_if_missing,   ('640141d4', 'Corin.BodyA.NormalMap.1024')),
    ],
    '640141d4': [
        (log,                           ('1.0: Corin BodyA, BearA NormalMap 1024p Hash',)),
        (multiply_section_if_missing,   ('289f4c58', 'Corin.BodyA.NormalMap.2048')),
    ],



    # MARK: Ellen
    'd44a8015': [(log, ('1.1: Ellen Hair IB Hash',)), (add_ib_check_if_missing,)],
    'e30fae03': [(log, ('1.1: Ellen Body IB Hash',)), (add_ib_check_if_missing,)],
    'f6ef8f3a': [(log, ('1.1: Ellen Face IB Hash',)), (add_ib_check_if_missing,)],

    '9c7fac5a': [(log, ('1.0 -> 1.1: Ellen Face IB Hash',)),       (update_hash, ('f6ef8f3a',))],
    '7f89a2b3': [(log, ('1.0 -> 1.1: Ellen Hair IB Hash',)),       (update_hash, ('d44a8015',))],
    'a72cfb34': [(log, ('1.0 -> 1.1: Ellen Body IB Hash',)),       (update_hash, ('e30fae03',))],


    '83dfd744': [(log, ('1.0 -> 1.1: Ellen Face Texcoord Hash',)), (update_hash, ('8744badf',))],


    'd59a5fec': [(log, ('1.0 -> 1.1: Ellen Hair Draw Hash',)),     (update_hash, ('77ac5f85',))],
    'a5448398': [(log, ('1.0 -> 1.1: Ellen Hair Position Hash',)), (update_hash, ('ba0fe600',))],
    '9cddb082': [
        (log, ('1.0 -> 1.1: Ellen Hair Texcoord Hash',)),
        (update_hash, ('5c33833e',)),
        (log, ('+ Remapping texcoord buffer from stride 24 to 36',)),
        (zzz_13_remap_texcoord, ('11_Ellen_Hair', ('4B', '2e', '2f', '2e', '2e'), ('4f', '2e', '2f', '2e', '2e'))), # attention
    ],

    '5c33833e': [
        (log, ('1.1 -> 1.2: Ellen Hair Texcoord Hash',)),
        (update_hash, ('a27a8e1a',)),
        (log, ('+ Remapping texcoord buffer from stride 36 to 24',)),
        (zzz_12_shrink_texcoord_color, ('1.2',))
    ],
    '52188576': [
        (log,                         ('1.3 -> 1.4: Ellen Hair Blend Remap',)),
        (update_buffer_blend_indices, (
            '52188576',
            (34, 35, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 49, 50),
            (39, 34, 40, 35, 38, 42, 43, 44, 45, 46, 47, 41, 50, 49),
        )),
        (update_hash,                 ('e91c93e0',)),
    ],


    '7bd3f8c2': [(log, ('1.0 -> 1.1: Ellen Body Draw Hash',)),     (update_hash, ('cdce1fc2',))],
    '89d5fba4': [(log, ('1.0 -> 1.1: Ellen Body Position Hash',)), (update_hash, ('b78f3616',))],
    '26966844': [(log, ('1.0 -> 1.1: Ellen Body Texcoord Hash',)), (update_hash, ('5ac6d5ee',))],
    '89589539': [(log, ('1.5 -> 1.6: Ellen Body Blend Hash',)),    (update_hash, ('ed9cb852',))],


    '09d55bce': [(log, ('1.0 -> 1.1: Ellen FaceA Diffuse 2048p Hash',)), (update_hash, ('465a66eb',))],
    '465a66eb': [
        (log,                           ('1.1: Ellen FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('f6ef8f3a', '9c7fac5a'), 'Ellen.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('4808d050', 'e6b27e31'), 'Ellen.FaceA.Diffuse.1024')),
    ],
    'e6b27e31': [(log, ('1.0 -> 1.1: Ellen FaceA Diffuse 1024p Hash',)), (update_hash, ('4808d050',))],
    '4808d050': [
        (log,                           ('1.1: Ellen FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('f6ef8f3a', '9c7fac5a'), 'Ellen.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('465a66eb', '09d55bce'), 'Ellen.FaceA.Diffuse.2048')),
    ],


    '81ccd2e2': [
        (log,                           ('1.0: Ellen HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('d44a8015', '7f89a2b3'), 'Ellen.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1440e534', 'Ellen.HairA.Diffuse.1024')),
    ],
    '1440e534': [
        (log,                           ('1.0: Ellen HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('d44a8015', '7f89a2b3'), 'Ellen.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('81ccd2e2', 'Ellen.HairA.Diffuse.2048')),
    ],
    'dc9d8b6e': [
        (log,                           ('1.0: Ellen HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        (('d44a8015', '7f89a2b3'), 'Ellen.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8c835faa', 'Ellen.HairA.LightMap.1024')),
    ],
    '8c835faa': [
        (log,                           ('1.0: Ellen HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        (('d44a8015', '7f89a2b3'), 'Ellen.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('dc9d8b6e', 'Ellen.HairA.LightMap.2048')),
    ],
    '01bb8189': [
        (log,                           ('1.0: Ellen HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        (('d44a8015', '7f89a2b3'), 'Ellen.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b21b8370', 'Ellen.HairA.MaterialMap.1024')),
    ],
    'b21b8370': [
        (log,                           ('1.0: Ellen HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        (('d44a8015', '7f89a2b3'), 'Ellen.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('01bb8189', 'Ellen.HairA.MaterialMap.2048')),
    ],
    'aaadca31': [
        (log,                           ('1.0: Ellen HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        (('d44a8015', '7f89a2b3'), 'Ellen.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d6715e09', 'Ellen.HairA.NormalMap.1024')),
    ],
    'd6715e09': [
        (log,                           ('1.0: Ellen HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        (('d44a8015', '7f89a2b3'), 'Ellen.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('aaadca31', 'Ellen.HairA.NormalMap.2048')),
    ],


    'cf5f5fed': [
        (log,                           ('1.0: -> 1.1: Ellen BodyA Diffuse 2048p Hash',)),
        (update_hash,                   ('163e2559',)),
    ],
    '163e2559': [
        (log,                           ('1.1: Ellen BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('e30fae03', 'a72cfb34'), 'Ellen.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('22fa0cd6', '94c15986'), 'Ellen.BodyA.Diffuse.1024')),
    ],
    '94c15986': [
        (log,                           ('1.0: -> 1.1: Ellen BodyA Diffuse 1024p Hash',)),
        (update_hash,                   ('22fa0cd6',)),
    ],
    '22fa0cd6': [
        (log,                           ('1.1: Ellen BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('e30fae03', 'a72cfb34'), 'Ellen.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('163e2559', 'cf5f5fed'), 'Ellen.BodyA.Diffuse.2048')),
    ],
    'ff26fb83': [
        (log,                           ('1.0: Ellen BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        (('e30fae03', 'a72cfb34'), 'Ellen.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('cea7516a', 'Ellen.BodyA.LightMap.1024')),
    ],
    'cea7516a': [
        (log,                           ('1.0: Ellen BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        (('e30fae03', 'a72cfb34'), 'Ellen.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ff26fb83', 'Ellen.BodyA.LightMap.2048')),
    ],
    'f4487235': [
        (log,                           ('1.0: Ellen BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        (('e30fae03', 'a72cfb34'), 'Ellen.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('30dc14d7', 'Ellen.BodyA.MaterialMap.1024')),
    ],
    '30dc14d7': [
        (log,                           ('1.0: Ellen BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        (('e30fae03', 'a72cfb34'), 'Ellen.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f4487235', 'Ellen.BodyA.MaterialMap.2048')),
    ],
    '798c3a51': [
        (log,                           ('1.0: Ellen BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        (('e30fae03', 'a72cfb34'), 'Ellen.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('590880e5', 'Ellen.BodyA.NormalMap.1024')),
    ],
    '590880e5': [
        (log,                           ('1.0: Ellen BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        (('e30fae03', 'a72cfb34'), 'Ellen.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('798c3a51', 'Ellen.BodyA.NormalMap.2048')),
    ],



    # MARK: EllenSkin
    'f601f643': [(log, ('1.5: EllenSkin Hair IB Hash',)), (add_ib_check_if_missing,)],
    '4a938c0a': [(log, ('1.5: EllenSkin Body IB Hash',)), (add_ib_check_if_missing,)],
    'fafcfe36': [(log, ('1.5: EllenSkin Tail IB Hash',)), (add_ib_check_if_missing,)],


    '0de025b4': [(log, ('1.5 -> 2.0: EllenSkin HairA MaterialMap 2048p Hash',)), (update_hash, ('8740602f',))],
    '0cf3cd79': [(log, ('1.5 -> 2.0: EllenSkin HairA MaterialMap 1024p Hash',)), (update_hash, ('0ab940d8',))],

    '6e15911b': [
        (log,                           ('1.5: EllenSkin HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('f601f643', 'EllenSkin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('37eefb17', 'EllenSkin.HairA.Diffuse.1024')),
    ],
    '37eefb17': [
        (log,                           ('1.5: EllenSkin HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('f601f643', 'EllenSkin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6e15911b', 'EllenSkin.HairA.Diffuse.2048')),
    ],
    '48fd827b': [
        (log,                           ('1.5: EllenSkin HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('f601f643', 'EllenSkin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('aa77b3ff', 'EllenSkin.HairA.LightMap.1024')),
    ],
    'aa77b3ff': [
        (log,                           ('1.5: EllenSkin HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('f601f643', 'EllenSkin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('48fd827b', 'EllenSkin.HairA.LightMap.2048')),
    ],
    '8740602f': [
        (log,                           ('2.0: EllenSkin HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('f601f643', 'EllenSkin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('0ab940d8', '0cf3cd79'), 'EllenSkin.HairA.MaterialMap.1024')),
    ],
    '0ab940d8': [
        (log,                           ('2.0: EllenSkin HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('f601f643', 'EllenSkin.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('8740602f', '0de025b4'), 'EllenSkin.HairA.MaterialMap.2048')),
    ],


    'd08f1a54': [(log, ('1.5 -> 2.0: EllenSkin BodyA MaterialMap 2048p Hash',)), (update_hash, ('1d7b458d',))],
    'a4b66af3': [(log, ('1.5 -> 2.0: EllenSkin BodyA MaterialMap 1024p Hash',)), (update_hash, ('ae919d9f',))],

    '76f42184': [
        (log,                           ('1.5: EllenSkin BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('4a938c0a', 'EllenSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('61beec5c', 'EllenSkin.BodyA.Diffuse.1024')),
    ],
    '61beec5c': [
        (log,                           ('1.5: EllenSkin BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('4a938c0a', 'EllenSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('76f42184', 'EllenSkin.BodyA.Diffuse.2048')),
    ],
    'e6c9a6e1': [
        (log,                           ('1.5: EllenSkin BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('4a938c0a', 'EllenSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d13c6700', 'EllenSkin.BodyA.LightMap.1024')),
    ],
    'd13c6700': [
        (log,                           ('1.5: EllenSkin BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('4a938c0a', 'EllenSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e6c9a6e1', 'EllenSkin.BodyA.LightMap.2048')),
    ],
    '1d7b458d': [
        (log,                           ('2.0: EllenSkin BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('4a938c0a', 'EllenSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('ae919d9f', 'a4b66af3'), 'EllenSkin.BodyA.MaterialMap.1024')),
    ],
    'ae919d9f': [
        (log,                           ('2.0: EllenSkin BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('4a938c0a', 'EllenSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('1d7b458d', 'd08f1a54'), 'EllenSkin.BodyA.MaterialMap.2048')),
    ],


    'abb51170': [(log, ('1.5 -> 2.0: EllenSkin TailA MaterialMap 2048p Hash',)), (update_hash, ('51cc39d5',))],
    'beb3f207': [(log, ('1.5 -> 2.0: EllenSkin TailA MaterialMap 1024p Hash',)), (update_hash, ('cf37068c',))],

    '0e474202': [
        (log,                           ('1.5: EllenSkin TailA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('fafcfe36', 'EllenSkin.Tail.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8df52d2a', 'EllenSkin.TailA.Diffuse.1024')),
    ],
    '8df52d2a': [
        (log,                           ('1.5: EllenSkin TailA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('fafcfe36', 'EllenSkin.Tail.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0e474202', 'EllenSkin.TailA.Diffuse.2048')),
    ],
    '8f2cb44d': [
        (log,                           ('1.5: EllenSkin TailA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('fafcfe36', 'EllenSkin.Tail.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a2f7a7db', 'EllenSkin.TailA.LightMap.1024')),
    ],
    'a2f7a7db': [
        (log,                           ('1.5: EllenSkin TailA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('fafcfe36', 'EllenSkin.Tail.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8f2cb44d', 'EllenSkin.TailA.LightMap.2048')),
    ],
    '51cc39d5': [
        (log,                           ('2.0: EllenSkin TailA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('fafcfe36', 'EllenSkin.Tail.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('cf37068c', 'beb3f207'), 'EllenSkin.TailA.MaterialMap.1024')),
    ],
    'cf37068c': [
        (log,                           ('2.0: EllenSkin TailA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('fafcfe36', 'EllenSkin.Tail.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('51cc39d5', 'abb51170'), 'EllenSkin.TailA.MaterialMap.2048')),
    ],



    # MARK: Evelyn
    '10a5bde2': [(log, ('1.5: Evelyn Hair IB Hash',)),      (add_ib_check_if_missing,)],
    '04b53ecd': [(log, ('1.5: Evelyn Body IB Hash',)),      (add_ib_check_if_missing,)],
    'bb6d1023': [(log, ('1.5: Evelyn Jacket IB Hash',)),    (add_ib_check_if_missing,)],
    'b3eaedb0': [(log, ('1.5: Evelyn Shoulders IB Hash',)), (add_ib_check_if_missing,)],
    'ddf4efa6': [(log, ('1.5: Evelyn Face IB Hash',)),      (add_ib_check_if_missing,)],

    '8e1d1a6f': [
        (log,                           ('1.5: Evelyn FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('ddf4efa6', 'Evelyn.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('bc090438', 'Evelyn.FaceA.Diffuse.1024')),
    ],
    'bc090438': [
        (log,                           ('1.5: Evelyn FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('ddf4efa6', 'Evelyn.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8e1d1a6f', 'Evelyn.FaceA.Diffuse.2048')),
    ],


    '0e5c3c97': [
        (log,                           ('1.5: Evelyn Hair, Jacket Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   ('65a7592d', 'Evelyn.Hair.Diffuse.1024')),
    ],
    'e1434e0d': [
        (log,                           ('1.5: Evelyn Hair, Jacket LightMap 2048p Hash',)),
        (multiply_section_if_missing,   ('eb414a98', 'Evelyn.Hair.LightMap.1024')),
    ],
    'b2718585': [
        (log,                           ('1.5: Evelyn Hair, Jacket MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   ('e680f0c7', 'Evelyn.Hair.MaterialMap.1024')),
    ],
    '65a7592d': [
        (log,                           ('1.5: Evelyn Hair, Jacket Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   ('0e5c3c97', 'Evelyn.Hair.Diffuse.2048')),
    ],
    'eb414a98': [
        (log,                           ('1.5: Evelyn Hair, Jacket LightMap 1024p Hash',)),
        (multiply_section_if_missing,   ('e1434e0d', 'Evelyn.Hair.LightMap.2048')),
    ],
    'e680f0c7': [
        (log,                           ('1.5: Evelyn Hair, Jacket MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   ('b2718585', 'Evelyn.Hair.MaterialMap.2048')),
    ],

    'a59b14c0': [
        (log,                           ('1.5: Evelyn Body, Shoulder Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   ('93033898', 'Evelyn.Body.Diffuse.1024')),
    ],
    'd022d32c': [
        (log,                           ('1.5: Evelyn Body, Shoulder LightMap 2048p Hash',)),
        (multiply_section_if_missing,   ('16aab2ab', 'Evelyn.Body.LightMap.1024')),
    ],
    '8624e4e4': [
        (log,                           ('1.5: Evelyn Body, Shoulder MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   ('716561f0', 'Evelyn.Body.MaterialMap.1024')),
    ],
    '93033898': [
        (log,                           ('1.5: Evelyn Body, Shoulder Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   ('a59b14c0', 'Evelyn.Body.Diffuse.2048')),
    ],
    '16aab2ab': [
        (log,                           ('1.5: Evelyn Body, Shoulder LightMap 1024p Hash',)),
        (multiply_section_if_missing,   ('d022d32c', 'Evelyn.Body.LightMap.2048')),
    ],
    '716561f0': [
        (log,                           ('1.5: Evelyn Body, Shoulder MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   ('8624e4e4', 'Evelyn.Body.MaterialMap.2048')),
    ],



    # MARK: Grace
    '89299f56': [(log, ('1.0: Grace Hair IB Hash',)), (add_ib_check_if_missing,)],
    '8b240678': [(log, ('1.2: Grace Body IB Hash',)), (add_ib_check_if_missing,)],
    '4d60568b': [(log, ('1.0: Grace Face IB Hash',)), (add_ib_check_if_missing,)],


    # reverted in 1.2
    # '89d903ba': [
    #     (log, ('1.0: -> 1.1: Grace Hair Texcoord Hash',)),
    #     (update_hash, ('d21f32ad',)),
    #     (log, ('+ Remapping texcoord buffer from stride 20 to 32',)),
    #     (update_buffer_element_width, (('BBBB', 'ee', 'ff', 'ee'), ('ffff', 'ee', 'ff', 'ee'), '1.1')),
    #     (log, ('+ Setting texcoord vcolor alpha to 1',)),
    #     (update_buffer_element_value, (('ffff', 'ee', 'ff', 'ee'), ('xxx1', 'xx', 'xx', 'xx'), '1.1'))
    # ],

    'd21f32ad': [
        (log, ('1.1 -> 1.2: Grace Hair Texcoord Hash',)),
        (update_hash, ('89d903ba',)),
        (log, ('+ Remapping texcoord buffer',)),
        (zzz_12_shrink_texcoord_color, ('1.2',))
    ],

    'e5e04f6f': [(log, ('1.1 -> 1.2: Grace Body Draw Hash',)),     (update_hash, ('f1cba806',))],
    '26ffa186': [
        (log, ('1.1 -> 1.2: Grace Body Position Hash',)),
        (update_hash, ('8855c5cf',)),
        (log, ('1.1 -> 1.2: Grace Body Blend Remap',)),
        (update_buffer_blend_indices, (
            '8855c5cf',
            (35, 34, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67,  68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89),
            (34, 35, 80, 85, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 51, 47, 48, 49, 50, 52, 54, 53, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 66,  65, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 89, 78, 79, 81, 82, 83, 84, 86, 87, 88),
        ))
    ],
    'e536af35': [(log, ('1.1 -> 1.2: Grace Body Texcoord Hash',)), (update_hash, ('4bb45448',))],
    '0f82a13e': [
        (log, ('1.1 -> 1.2: Grace Body IB Hash',)),
        (update_hash, ('8b240678',)),
        (transfer_indexed_sections, {
            'src_indices': ['0', '42885'],
            'trg_indices': ['0', '42927'],
        })
    ],


    'e75590cb': [
        (log,                           ('1.0: Grace FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('4d60568b', 'Grace.FaceA.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7459ecf4', 'Grace.FaceA.Diffuse.2048')),
    ],
    '7459ecf4': [
        (log,                           ('1.0: Grace FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('4d60568b', 'Grace.FaceA.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e75590cb', 'Grace.FaceA.Diffuse.1024')),
    ],


    '8eddd041': [(log, ('1.0 -> 2.0: Grace HairA LightMap 2048p Hash',)),           (update_hash, ('a22d2c2c',))],
    '26bf1588': [(log, ('1.0 -> 2.0: Grace HairA LightMap 1024p Hash',)),           (update_hash, ('48c17612',))],
    '3a38f6f9': [(log, ('1.0 -> 2.0: Grace HairA MaterialMap 2048p Hash',)),        (update_hash, ('7bb81a4f',))],
    'e1cb3739': [(log, ('1.0 -> 2.0: Grace HairA MaterialMap 1024p Hash',)),        (update_hash, ('381930fe',))],


    'a87d2822': [
        (log,                           ('1.0: Grace HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('89299f56', 'Grace.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('94d04401', 'Grace.HairA.Diffuse.1024')),
    ],
    '94d04401': [
        (log,                           ('1.0: Grace HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('89299f56', 'Grace.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a87d2822', 'Grace.HairA.Diffuse.2048')),
    ],
    'a22d2c2c': [
        (log,                           ('2.0: Grace HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('89299f56', 'Grace.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('48c17612', '26bf1588'), 'Grace.HairA.LightMap.1024')),
    ],
    '48c17612': [
        (log,                           ('2.0: Grace HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('89299f56', 'Grace.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('a22d2c2c', '8eddd041'), 'Grace.HairA.LightMap.2048')),
    ],
    '7bb81a4f': [
        (log,                           ('2.0: Grace HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('89299f56', 'Grace.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('381930fe', 'e1cb3739'), 'Grace.HairA.MaterialMap.1024')),
    ],
    '381930fe': [
        (log,                           ('2.0: Grace HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('89299f56', 'Grace.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('7bb81a4f', '3a38f6f9'), 'Grace.HairA.MaterialMap.2048')),
    ],
    '846fab9a': [
        (log,                           ('1.0: Grace HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('89299f56', 'Grace.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1c4079f7', 'Grace.HairA.NormalMap.1024')),
    ],
    '1c4079f7': [
        (log,                           ('1.0: Grace HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('89299f56', 'Grace.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('846fab9a', 'Grace.HairA.NormalMap.2048')),
    ],


    '993fe3e1': [(log, ('1.0 -> 2.0: Grace BodyA LightMap 2048p Hash',)),           (update_hash, ('895fa458',))],
    '59dd8899': [(log, ('1.0 -> 2.0: Grace BodyA LightMap 1024p Hash',)),           (update_hash, ('7e2e15b3',))],


    '6d6ac4f4': [
        (log,                           ('1.0: Grace BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('397a8aed', 'Grace.BodyA.Diffuse.1024')),
    ],
    '397a8aed': [
        (log,                           ('1.0: Grace BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6d6ac4f4', 'Grace.BodyA.Diffuse.2048')),
    ],
    '895fa458': [
        (log,                           ('2.0: Grace BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('7e2e15b3', '59dd8899'), 'Grace.BodyA.LightMap.1024')),
    ],
    '7e2e15b3': [
        (log,                           ('2.0: Grace BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('895fa458', '993fe3e1'), 'Grace.BodyA.LightMap.2048')),
    ],
    'e8345f2c': [
        (log,                           ('1.0: Grace BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a6c8c203', 'Grace.BodyA.MaterialMap.1024')),
    ],
    'a6c8c203': [
        (log,                           ('1.0: Grace BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e8345f2c', 'Grace.BodyA.MaterialMap.2048')),
    ],
    '1e794b69': [
        (log,                           ('1.0: Grace BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9abd7824', 'Grace.BodyA.NormalMap.1024')),
    ],
    '9abd7824': [
        (log,                           ('1.0: Grace BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1e794b69', 'Grace.BodyA.NormalMap.2048')),
    ],
    '210b3ebf': [(log, ('1.3 -> 1.4: Grace BodyB Diffuse 2048p Hash',)), (update_hash, ('9c7057e8',))],
    '9c7057e8': [
        (log,                           ('1.4: Grace BodyB Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('ac361185', '21794bd6'), 'Grace.BodyB.Diffuse.1024')),
    ],
    '21794bd6': [(log, ('1.3 -> 1.4: Grace BodyB Diffuse 1024p Hash',)), (update_hash, ('ac361185',))],
    'ac361185': [
        (log,                           ('1.4: Grace BodyB Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('9c7057e8', '210b3ebf'), 'Grace.BodyB.Diffuse.2048')),
    ],
    '08082f5f': [
        (log,                           ('1.0: Grace BodyB LightMap 2048p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a60162a0', 'Grace.BodyB.LightMap.1024')),
    ],
    'a60162a0': [
        (log,                           ('1.0: Grace BodyB LightMap 1024p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('08082f5f', 'Grace.BodyB.LightMap.2048')),
    ],
    'f176398a': [
        (log,                           ('1.0: Grace BodyB MaterialMap 2048p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b5b88a3f', 'Grace.BodyB.MaterialMap.1024')),
    ],
    'b5b88a3f': [
        (log,                           ('1.0: Grace BodyB MaterialMap 1024p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f176398a', 'Grace.BodyB.MaterialMap.2048')),
    ],
    '06cb1413': [
        (log,                           ('1.0: Grace BodyB NormalMap 2048p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c5f703be', 'Grace.BodyB.NormalMap.1024')),
    ],
    'c5f703be': [
        (log,                           ('1.0: Grace BodyB NormalMap 1024p Hash',)),
        (add_section_if_missing,        (('8b240678', '0f82a13e'), 'Grace.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('06cb1413', 'Grace.BodyB.NormalMap.2048')),
    ],



    # MARK: Harumasa
    '78bea30d': [(log, ('1.4 -> 1.5: Harumasa Body IB Hash',)), (update_hash, ('79679a10',))],

    '6324de38': [(log, ('1.4: Harumasa Hair IB Hash',)), (add_ib_check_if_missing,)],
    '79679a10': [(log, ('1.4: Harumasa Body IB Hash',)), (add_ib_check_if_missing,)],
    'aa7ba2dc': [(log, ('1.4: Harumasa Legs IB Hash',)), (add_ib_check_if_missing,)],
    'b0688334': [(log, ('1.4: Harumasa Face IB Hash',)), (add_ib_check_if_missing,)],


    'cafffd37': [(log, ('1.4 -> 1.5: Harumasa Body Draw Hash',)),     (update_hash, ('1fb92e46',))],
    '3fa41462': [(log, ('1.4 -> 1.5: Harumasa Body Position Hash',)), (update_hash, ('0899751e',))],
    'c0b32d17': [(log, ('1.4 -> 1.5: Harumasa Body Blend Hash',)),    (update_hash, ('347a0e9d',))],
    '95ee1030': [(log, ('1.4 -> 1.5: Harumasa Body Texcoord Hash',)), (update_hash, ('e14fbc30',))],


    '4394c0b2': [
        (log,                           ('1.4: Harumasa FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('b0688334', 'Harumasa.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c5596262', 'Harumasa.FaceA.Diffuse.1024')),
    ],
    'c5596262': [
        (log,                           ('1.4: Harumasa FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('b0688334', 'Harumasa.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4394c0b2', 'Harumasa.FaceA.Diffuse.2048')),
    ],


    'd4838b9d': [(log, ('1.4 -> 2.0: Harumasa HairA LightMap 2048p Hash',)),        (update_hash, ('11041778',))],
    'a1310b4f': [(log, ('1.4 -> 2.0: Harumasa HairA LightMap 1024p Hash',)),        (update_hash, ('54cc6a9a',))],


    'b8f268ee': [
        (log,                           ('1.4: Harumasa HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('6324de38', 'Harumasa.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5700ced5', 'Harumasa.HairA.Diffuse.1024')),
    ],
    '5700ced5': [
        (log,                           ('1.4: Harumasa HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('6324de38', 'Harumasa.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b8f268ee', 'Harumasa.HairA.Diffuse.2048')),
    ],
    '11041778': [
        (log,                           ('2.0: Harumasa HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('6324de38', 'Harumasa.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('54cc6a9a', 'a1310b4f'), 'Harumasa.HairA.LightMap.1024')),
    ],
    '54cc6a9a': [
        (log,                           ('2.0: Harumasa HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('6324de38', 'Harumasa.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('11041778', 'd4838b9d'), 'Harumasa.HairA.LightMap.2048')),
    ],
    '7217c146': [
        (log,                           ('1.4: Harumasa HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('6324de38', 'Harumasa.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c2c9ad2d', 'Harumasa.HairA.MaterialMap.1024')),
    ],
    'c2c9ad2d': [
        (log,                           ('1.4: Harumasa HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('6324de38', 'Harumasa.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7217c146', 'Harumasa.HairA.MaterialMap.2048')),
    ],


    'ba52ac92': [(log, ('1.4 -> 1.5: Harumasa BodyA Diffuse 2048p Hash',)), (update_hash, ('49f8aaf6',))],
    'e0b0c6eb': [(log, ('1.4 -> 1.5: Harumasa BodyA Diffuse 1024p Hash',)), (update_hash, ('999ec526',))],
    'cd1e0187': [(log, ('1.4 -> 1.5: Harumasa BodyA MaterialMap 2048p Hash',)), (update_hash, ('6d105f7e',))],
    '2b0017d5': [(log, ('1.4 -> 1.5: Harumasa BodyA MaterialMap 1024p Hash',)), (update_hash, ('c90264db',))],


    '49f8aaf6': [
        (log,                           ('1.4: Harumasa BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('79679a10', '78bea30d'), 'Harumasa.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('999ec526', 'e0b0c6eb'), 'Harumasa.BodyA.Diffuse.1024')),
    ],
    '999ec526': [
        (log,                           ('1.4: Harumasa BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('79679a10', '78bea30d'), 'Harumasa.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('49f8aaf6', 'ba52ac92'), 'Harumasa.BodyA.Diffuse.2048')),
    ],
    'cc51476a': [
        (log,                           ('1.4: Harumasa BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        (('79679a10', '78bea30d'), 'Harumasa.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2b1230cf', 'Harumasa.BodyA.LightMap.1024')),
    ],
    '2b1230cf': [
        (log,                           ('1.4: Harumasa BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        (('79679a10', '78bea30d'), 'Harumasa.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('cc51476a', 'Harumasa.BodyA.LightMap.2048')),
    ],
    '6d105f7e': [
        (log,                           ('1.4: Harumasa BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        (('79679a10', '78bea30d'), 'Harumasa.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('c90264db', '2b0017d5'), 'Harumasa.BodyA.MaterialMap.1024')),
    ],
    'c90264db': [
        (log,                           ('1.4: Harumasa BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        (('79679a10', '78bea30d'), 'Harumasa.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('6d105f7e', 'cd1e0187'), 'Harumasa.BodyA.MaterialMap.2048')),
    ],


    'ba8e396b': [(log, ('1.4 -> 2.0: Harumasa LegsA MaterialMap 2048p Hash',)),     (update_hash, ('72885950',))],
    'bdbf66a1': [(log, ('1.4 -> 2.0: Harumasa LegsA MaterialMap 1024p Hash',)),     (update_hash, ('b84027c8',))],


    '44d74a1a': [
        (log,                           ('1.4: Harumasa LegsA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('aa7ba2dc', 'Harumasa.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('897c74d5', 'Harumasa.LegsA.Diffuse.1024')),
    ],
    '897c74d5': [
        (log,                           ('1.4: Harumasa LegsA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('aa7ba2dc', 'Harumasa.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('44d74a1a', 'Harumasa.LegsA.Diffuse.2048')),
    ],
    '4b4d0ff6': [
        (log,                           ('1.4: Harumasa LegsA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('aa7ba2dc', 'Harumasa.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('822ec07f', 'Harumasa.LegsA.LightMap.1024')),
    ],
    '822ec07f': [
        (log,                           ('1.4: Harumasa LegsA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('aa7ba2dc', 'Harumasa.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4b4d0ff6', 'Harumasa.LegsA.LightMap.2048')),
    ],
    '72885950': [
        (log,                           ('2.0: Harumasa LegsA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('aa7ba2dc', 'Harumasa.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('b84027c8', 'bdbf66a1'), 'Harumasa.LegsA.MaterialMap.1024')),
    ],
    'b84027c8': [
        (log,                           ('2.0: Harumasa LegsA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('aa7ba2dc', 'Harumasa.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('72885950', 'ba8e396b'), 'Harumasa.LegsA.MaterialMap.2048')),
    ],



    # MARK: Hugo
    '45ae7079': [(log, ('1.7: Hugo Hair IB Hash',)), (add_ib_check_if_missing,)],
    'b4765894': [(log, ('1.7: Hugo Body IB Hash',)), (add_ib_check_if_missing,)],
    'ed26c53d': [(log, ('1.7: Hugo Coat IB Hash',)), (add_ib_check_if_missing,)],
    '5db95af3': [(log, ('1.7: Hugo Badge IB Hash',)), (add_ib_check_if_missing,)],
    '66b936fc': [(log, ('1.7: Hugo Face IB Hash',)), (add_ib_check_if_missing,)],

    # Face
    'a3064b0e': [
        (log,                           ('1.7: Hugo FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('66b936fc', 'Hugo.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0f344a22', 'Hugo.FaceA.Diffuse.1024')),
    ],
    '0f344a22': [
        (log,                           ('1.7: Hugo FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('66b936fc', 'Hugo.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a3064b0e', 'Hugo.FaceA.Diffuse.2048')),
    ],

    # Hair
    'f50ebb37': [
        (log,                           ('1.7: Hugo HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('45ae7079', 'Hugo.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('bab642c6', 'Hugo.HairA.Diffuse.1024')),
    ],
    'bab642c6': [
        (log,                           ('1.7: Hugo HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('45ae7079', 'Hugo.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f50ebb37', 'Hugo.HairA.Diffuse.2048')),
    ],
    '94daa8f7': [
        (log,                           ('1.7: Hugo HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('45ae7079', 'Hugo.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('dcf7c209', 'Hugo.HairA.LightMap.1024')),
    ],
    'dcf7c209': [
        (log,                           ('1.7: Hugo HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('45ae7079', 'Hugo.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('94daa8f7', 'Hugo.HairA.LightMap.2048')),
    ],
    '9614f191': [
        (log,                           ('1.7: Hugo HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('45ae7079', 'Hugo.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('144c15d0', 'Hugo.HairA.MaterialMap.1024')),
    ],
    '144c15d0': [
        (log,                           ('1.7: Hugo HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('45ae7079', 'Hugo.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9614f191', 'Hugo.HairA.MaterialMap.2048')),
    ],

    # Body
    '7fa5eb2e': [
        (log,                           ('1.7: Hugo BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2841b582', 'Hugo.BodyA.Diffuse.1024')),
    ],
    '2841b582': [
        (log,                           ('1.7: Hugo BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7fa5eb2e', 'Hugo.BodyA.Diffuse.2048')),
    ],
    'f9911f83': [
        (log,                           ('1.7: Hugo BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9fd99d99', 'Hugo.BodyA.LightMap.1024')),
    ],
    '9fd99d99': [
        (log,                           ('1.7: Hugo BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f9911f83', 'Hugo.BodyA.LightMap.2048')),
    ],
    'c6fa84c9': [
        (log,                           ('1.7: Hugo BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e2333ede', 'Hugo.BodyA.MaterialMap.1024')),
    ],
    'e2333ede': [
        (log,                           ('1.7: Hugo BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c6fa84c9', 'Hugo.BodyA.MaterialMap.2048')),
    ],

    # Coat
    '348bc40f': [
        (log,                           ('1.7: Hugo CoatA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('481e8fe0', 'Hugo.CoatA.Diffuse.1024')),
    ],
    '481e8fe0': [
        (log,                           ('1.7: Hugo CoatA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('348bc40f', 'Hugo.CoatA.Diffuse.2048')),
    ],
    '0db80414': [
        (log,                           ('1.7: Hugo CoatA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a951a0cf', 'Hugo.CoatA.LightMap.1024')),
    ],
    'a951a0cf': [
        (log,                           ('1.7: Hugo CoatA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0db80414', 'Hugo.CoatA.LightMap.2048')),
    ],
    '25b33389': [
        (log,                           ('1.7: Hugo CoatA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ec648dcb', 'Hugo.CoatA.MaterialMap.1024')),
    ],
    'ec648dcb': [
        (log,                           ('1.7: Hugo CoatA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('b4765894', 'Hugo.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('25b33389', 'Hugo.CoatA.MaterialMap.2048')),
    ],



    # MARK: Jane Doe
    '9268a5af': [(log, ('1.4: Jane Hair IB Hash',)), (add_ib_check_if_missing,)],
    'ba4255a5': [(log, ('1.4: Jane Body IB Hash',)), (add_ib_check_if_missing,)],
    'ef86fc9f': [(log, ('1.1: Jane Face IB Hash',)), (add_ib_check_if_missing,)],

    'c8ad344e': [
        (log, ('1.1 -> 1.2: Jane Hair Texcoord Hash',)),
        (update_hash, ('257a90d6',)),
        (log, ('+ Remapping texcoord buffer',)),
        (zzz_12_shrink_texcoord_color, ('1.2',))
    ],

    '5721e4e7': [(log, ('1.3 -> 1.4: Jane Hair Draw Hash',)),     (update_hash, ('2d06e785',)),],
    '24323bf9': [(log, ('1.3 -> 1.4: Jane Hair Position Hash',)), (update_hash, ('e7a3b7dc',)),],
    '0a10c747': [(log, ('1.3 -> 1.4: Jane Hair Blend Hash',)),    (update_hash, ('8721477f',)),],
    '257a90d6': [(log, ('1.3 -> 1.4: Jane Hair Texcoord Hash',)), (update_hash, ('acec29f8',)),],
    '7b16a708': [(log, ('1.3 -> 1.4: Jane Hair IB Hash',)),       (update_hash, ('9268a5af',)),],

    'd1aa4b85': [(log, ('1.3 -> 1.4: Jane Body Draw Hash',)),     (update_hash, ('0e1c6740',)),],
    '06f9bc49': [(log, ('1.3 -> 1.4: Jane Body Position Hash',)), (update_hash, ('10050266',)),],
    '9727a184': [(log, ('1.3 -> 1.4: Jane Body Blend Hash',)),    (update_hash, ('e27f398e',)),],
    '8b85c03e': [(log, ('1.3 -> 1.4: Jane Body Texcoord Hash',)), (update_hash, ('949549de',)),],
    'e2c0144e': [(log, ('1.3 -> 1.4: Jane Body IB Hash',)),       (update_hash, ('ba4255a5',)),],

    '689639a5': [(log, ('1.3 -> 1.4: Jane FaceA Diffuse 1024p Hash',)), (update_hash, ('d823ac80',)),],
    'd823ac80': [
        (log,                           ('1.1: Jane FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('ef86fc9f', 'Jane.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('3b75aa2c', '8974fb74'), 'Jane.FaceA.Diffuse.2048')),
    ],
    '8974fb74': [(log, ('1.3 -> 1.4: Jane FaceA Diffuse 2048p Hash',)), (update_hash, ('3b75aa2c',)),],
    '3b75aa2c': [
        (log,                           ('1.1: Jane FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('ef86fc9f', 'Jane.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('d823ac80', '689639a5'), 'Jane.FaceA.Diffuse.1024')),
    ],

    'f7ef1a53': [
        (log,                           ('1.1: Jane HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('9268a5af', '7b16a708'), 'Jane.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b33a9770', 'Jane.HairA.Diffuse.1024')),
    ],
    'b33a9770': [
        (log,                           ('1.1: Jane HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('9268a5af', '7b16a708'), 'Jane.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f7ef1a53', 'Jane.HairA.Diffuse.2048')),
    ],
    '9ec4cd4f': [
        (log,                           ('1.1: Jane HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        (('9268a5af', '7b16a708'), 'Jane.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5e12acc1', 'Jane.HairA.LightMap.1024')),
    ],
    '5e12acc1': [
        (log,                           ('1.1: Jane HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        (('9268a5af', '7b16a708'), 'Jane.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9ec4cd4f', 'Jane.HairA.LightMap.2048')),
    ],
    '5e34e275': [
        (log,                           ('1.1: Jane HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        (('9268a5af', '7b16a708'), 'Jane.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('40fca454', 'Jane.HairA.MaterialMap.1024')),
    ],
    '40fca454': [
        (log,                           ('1.1: Jane HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        (('9268a5af', '7b16a708'), 'Jane.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5e34e275', 'Jane.HairA.MaterialMap.2048')),
    ],
    '4aa12b36': [
        (log,                           ('1.1: Jane HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        (('9268a5af', '7b16a708'), 'Jane.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f0aded31', 'Jane.HairA.NormalMap.1024')),
    ],
    'f0aded31': [
        (log,                           ('1.1: Jane HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        (('9268a5af', '7b16a708'), 'Jane.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4aa12b36', 'Jane.HairA.NormalMap.2048')),
    ],

    'd1f56c7d': [
        (log,                           ('1.1: Jane BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('ba4255a5', 'e2c0144e'), 'Jane.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e62ae3b5', 'Jane.BodyA.Diffuse.1024')),
    ],
    'e62ae3b5': [
        (log,                           ('1.1: Jane BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('ba4255a5', 'e2c0144e'), 'Jane.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d1f56c7d', 'Jane.BodyA.Diffuse.2048')),
    ],
    '3087f82a': [
        (log,                           ('1.1: Jane BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        (('ba4255a5', 'e2c0144e'), 'Jane.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('52fa9861', 'Jane.BodyA.LightMap.1024')),
    ],
    '52fa9861': [
        (log,                           ('1.1: Jane BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        (('ba4255a5', 'e2c0144e'), 'Jane.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3087f82a', 'Jane.BodyA.LightMap.2048')),
    ],
    '99eae42e': [
        (log,                           ('1.1: Jane BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        (('ba4255a5', 'e2c0144e'), 'Jane.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5dce2408', 'Jane.BodyA.MaterialMap.1024')),
    ],
    '5dce2408': [
        (log,                           ('1.1: Jane BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        (('ba4255a5', 'e2c0144e'), 'Jane.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('99eae42e', 'Jane.BodyA.MaterialMap.2048')),
    ],
    '0165f71c': [
        (log,                           ('1.1: Jane BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        (('ba4255a5', 'e2c0144e'), 'Jane.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('387dfc9f', 'Jane.BodyA.NormalMap.1024')),
    ],
    '387dfc9f': [
        (log,                           ('1.1: Jane BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        (('ba4255a5', 'e2c0144e'), 'Jane.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0165f71c', 'Jane.BodyA.NormalMap.2048')),
    ],



    # MARK: JuFufu
    'a4fd9113': [(log, ('2.0: JuFufu Hair IB Hash',)), (add_ib_check_if_missing,)],
    'de303163': [(log, ('2.0: JuFufu Body IB Hash',)), (add_ib_check_if_missing,)],
    'f8ab3141': [(log, ('2.0: JuFufu Tail IB Hash',)), (add_ib_check_if_missing,)],
    '321768df': [(log, ('2.0: JuFufu Face IB Hash',)), (add_ib_check_if_missing,)],


    '37b277db': [
        (log,                           ('2.0: JuFufu FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('321768df', 'JuFufu.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('134fbe43', 'JuFufu.FaceA.Diffuse.1024')),
    ],
    '134fbe43': [
        (log,                           ('2.0: JuFufu FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('321768df', 'JuFufu.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('37b277db', 'JuFufu.FaceA.Diffuse.2048')),
    ],


    'db3bdffa': [
        (log,                           ('2.0: JuFufu HairA TailA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('a4fd9113', 'JuFufu.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('521f60ae', 'JuFufu.HairA.Diffuse.1024')),
    ],
    '521f60ae': [
        (log,                           ('2.0: JuFufu HairA TailA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('a4fd9113', 'JuFufu.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('db3bdffa', 'JuFufu.HairA.Diffuse.2048')),
    ],
    '5c948f7b': [
        (log,                           ('2.0: JuFufu HairA TailA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('a4fd9113', 'JuFufu.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('29bb13b7', 'JuFufu.HairA.LightMap.1024')),
    ],
    '29bb13b7': [
        (log,                           ('2.0: JuFufu HairA TailA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('a4fd9113', 'JuFufu.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5c948f7b', 'JuFufu.HairA.LightMap.2048')),
    ],
    '9f4d4f72': [
        (log,                           ('2.0: JuFufu HairA TailA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('a4fd9113', 'JuFufu.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9355dcea', 'JuFufu.HairA.MaterialMap.1024')),
    ],
    '9355dcea': [
        (log,                           ('2.0: JuFufu HairA TailA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('a4fd9113', 'JuFufu.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9f4d4f72', 'JuFufu.HairA.MaterialMap.2048')),
    ],


    '16e4cac1': [
        (log,                           ('2.0: JuFufu BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('de303163', 'JuFufu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3b372932', 'JuFufu.BodyA.Diffuse.1024')),
    ],
    '3b372932': [
        (log,                           ('2.0: JuFufu BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('de303163', 'JuFufu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('16e4cac1', 'JuFufu.BodyA.Diffuse.2048')),
    ],
    'c952431f': [
        (log,                           ('2.0: JuFufu BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('de303163', 'JuFufu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9d1ab7c4', 'JuFufu.BodyA.LightMap.1024')),
    ],
    '9d1ab7c4': [
        (log,                           ('2.0: JuFufu BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('de303163', 'JuFufu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c952431f', 'JuFufu.BodyA.LightMap.2048')),
    ],
    'd555b4f8': [
        (log,                           ('2.0: JuFufu BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('de303163', 'JuFufu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f72af17c', 'JuFufu.BodyA.MaterialMap.1024')),
    ],
    'f72af17c': [
        (log,                           ('2.0: JuFufu BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('de303163', 'JuFufu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d555b4f8', 'JuFufu.BodyA.MaterialMap.2048')),
    ],



    # MARK: Koleda
    '242a8d48': [(log, ('1.0: Koleda Hair IB Hash',)), (add_ib_check_if_missing,)],
    '3afb3865': [(log, ('1.0: Koleda Body IB Hash',)), (add_ib_check_if_missing,)],
    '0e74656e': [(log, ('1.0: Koleda Face IB Hash',)), (add_ib_check_if_missing,)],

    '1a9b182a': [
        (log,            ('1.2 -> 1.3: Koleda Hair Texcoord Hash',)),
        (update_hash,    ('e35571a9',)),
        (log,            ('+ Remapping texcoord buffer',)),
        (zzz_13_remap_texcoord, (
            '13_koleda_hair',
            ('4B','2e','2f','2e'),
            ('4B','2f','2f','2f')
        )),
    ],
    'e3021a32': [
        (log,            ('1.2 -> 1.3: Koleda Body Texcoord Hash',)),
        (update_hash,    ('38b31082',)),
        (log,            ('+ Remapping texcoord buffer',)),
        (zzz_13_remap_texcoord, (
            '13_koleda_body',
            ('4B','2e','2f','2e'),
            ('4B','2f','2f','2f')
        )),
    ],

    'f1045670': [
        (log,                           ('1.0: Koleda FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('0e74656e', 'Koleda.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('200db5c4', 'Koleda.FaceA.Diffuse.2048')),
    ],
    '200db5c4': [
        (log,                           ('1.0: Koleda FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('0e74656e', 'Koleda.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f1045670', 'Koleda.FaceA.Diffuse.1024')),
    ],


    '8042506d': [(log, ('1.0 -> 2.0: Koleda HairA LightMap 2048p Hash',)),           (update_hash, ('a451ca03',))],
    '144ab293': [(log, ('1.0 -> 2.0: Koleda HairA LightMap 1024p Hash',)),           (update_hash, ('1b33709a',))],


    'e8e89f00': [
        (log,                           ('1.0: Koleda HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('242a8d48', 'Koleda.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b0046e5a', 'Koleda.HairA.Diffuse.1024')),
    ],
    'b0046e5a': [
        (log,                           ('1.0: Koleda HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('242a8d48', 'Koleda.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e8e89f00', 'Koleda.HairA.Diffuse.2048')),
    ],
    'a451ca03': [
        (log,                           ('2.0: Koleda HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('242a8d48', 'Koleda.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('1b33709a', '144ab293'), 'Koleda.HairA.LightMap.1024')),
    ],
    '1b33709a': [
        (log,                           ('2.0: Koleda HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('242a8d48', 'Koleda.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('a451ca03', '8042506d'), 'Koleda.HairA.LightMap.2048')),
    ],
    'd1aac666': [
        (log,                           ('1.0: Koleda HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('242a8d48', 'Koleda.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7a46b52a', 'Koleda.HairA.NormalMap.1024')),
    ],
    '7a46b52a': [
        (log,                           ('1.0: Koleda HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('242a8d48', 'Koleda.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d1aac666', 'Koleda.HairA.NormalMap.2048')),
    ],


    '78e0f9f5': [(log, ('1.0 -> 2.0: Koleda BodyA LightMap 2048p Hash',)),          (update_hash, ('7c1bce32',))],
    'db58787e': [(log, ('1.0 -> 2.0: Koleda BodyA LightMap 1024p Hash',)),          (update_hash, ('a1087d61',))],
    '6f34885f': [(log, ('1.0 -> 2.0: Koleda BodyA MaterialMap 2048p Hash',)),       (update_hash, ('b60ace0c',))],
    '02e6cb95': [(log, ('1.0 -> 2.0: Koleda BodyA MaterialMap 1024p Hash',)),       (update_hash, ('1c162e9c',))],


    '337fd6a2': [
        (log,                           ('1.0: Koleda BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('3afb3865', 'Koleda.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ce10237d', 'Koleda.BodyA.Diffuse.1024')),
    ],
    'ce10237d': [
        (log,                           ('1.0: Koleda BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('3afb3865', 'Koleda.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('337fd6a2', 'Koleda.BodyA.Diffuse.2048')),
    ],
    '7c1bce32': [
        (log,                           ('2.0: Koleda BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('3afb3865', 'Koleda.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('a1087d61', 'db58787e'), 'Koleda.BodyA.LightMap.1024')),
    ],
    'a1087d61': [
        (log,                           ('2.0: Koleda BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('3afb3865', 'Koleda.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('7c1bce32', '78e0f9f5'), 'Koleda.BodyA.LightMap.2048')),
    ],
    'b60ace0c': [
        (log,                           ('2.0: Koleda BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('3afb3865', 'Koleda.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('1c162e9c', '02e6cb95'), 'Koleda.BodyA.MaterialMap.1024')),
    ],
    '1c162e9c': [
        (log,                           ('2.0: Koleda BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('3afb3865', 'Koleda.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('b60ace0c', '6f34885f'), 'Koleda.BodyA.MaterialMap.2048')),
    ],
    'e71d134f': [
        (log,                           ('1.0: Koleda BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('3afb3865', 'Koleda.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0914d3d3', 'Koleda.BodyA.NormalMap.1024')),
    ],
    '0914d3d3': [
        (log,                           ('1.0: Koleda BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('3afb3865', 'Koleda.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e71d134f', 'Koleda.BodyA.NormalMap.2048')),
    ],


    # MARK: Lighter
    '542b8aa9': [(log, ('1.3: Lighter Hair IB Hash',)),    (add_ib_check_if_missing,)],
    '8899e0fd': [(log, ('1.3: Lighter Body IB Hash',)),    (add_ib_check_if_missing,)],
    '018b03f0': [(log, ('1.3: Lighter Arm IB Hash',)),     (add_ib_check_if_missing,)],

    '039f30cf': [(log, ('1.3 -> 1.4: Lighter Face IB Hash',)), (update_hash, ('dcc7bb78',))],
    'dcc7bb78': [(log, ('1.4: Lighter Face IB Hash',)),        (add_ib_check_if_missing,)],

    '0baec6b7': [(log, ('1.3 -> 1.4: Lighter Body Position Hash',)), (update_hash, ('5e461440',))],
    '710bca71': [(log, ('1.3 -> 1.4: Lighter Body Texcoord Hash',)), (update_hash, ('25ad7289',))],
    'af2e48a6': [(log, ('1.3 -> 1.4: Lighter Arm Texcoord Hash',)),  (update_hash, ('88aecee2',))],

    '5e461440': [(log, ('1.5 -> 1.6: Lighter Body Position Hash',)),  (update_hash, ('f6bbabb5',))],
    '25ad7289': [(log, ('1.5 -> 1.6: Lighter Body Texcoord Hash',)),  (update_hash, ('e1ae7f38',))],

    '8ec33dd0': [
        (log,                           ('1.3: Lighter FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('dcc7bb78', '039f30cf'), 'Lighter.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4524e91a', 'Lighter.FaceA.Diffuse.2048')),
    ],
    '4524e91a': [
        (log,                           ('1.3: Lighter FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('dcc7bb78', '039f30cf'), 'Lighter.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8ec33dd0', 'Lighter.FaceA.Diffuse.1024')),
    ],

    '1cd2d442': [
        (log,                           ('1.3: Lighter HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('542b8aa9', 'Lighter.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c5d60a1d', 'Lighter.HairA.Diffuse.2048')),
    ],
    '62ec7f01': [
        (log,                           ('1.3: Lighter HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('542b8aa9', 'Lighter.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6d3f91bc', 'Lighter.HairA.LightMap.2048')),
    ],
    '8687f7b8': [
        (log,                           ('1.3: Lighter HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('542b8aa9', 'Lighter.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d5ba9ea6', 'Lighter.HairA.MaterialMap.2048')),
    ],
    'c5d60a1d': [
        (log,                           ('1.3: Lighter HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('542b8aa9', 'Lighter.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1cd2d442', 'Lighter.HairA.Diffuse.1024')),
    ],
    '6d3f91bc': [
        (log,                           ('1.3: Lighter HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('542b8aa9', 'Lighter.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('62ec7f01', 'Lighter.HairA.LightMap.1024')),
    ],
    'd5ba9ea6': [
        (log,                           ('1.3: Lighter HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('542b8aa9', 'Lighter.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8687f7b8', 'Lighter.HairA.MaterialMap.1024')),
    ],

    'be46890b': [
        (log,                           ('1.3: Lighter BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('8899e0fd', 'Lighter.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5ed96bf2', 'Lighter.BodyA.Diffuse.2048')),
    ],
    '5b828635': [
        (log,                           ('1.3: Lighter BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('8899e0fd', 'Lighter.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('da6f4dc0', 'Lighter.BodyA.LightMap.2048')),
    ],
    '65f3bb7c': [
        (log,                           ('1.3: Lighter BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('8899e0fd', 'Lighter.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('94aebd7e', 'Lighter.BodyA.MaterialMap.2048')),
    ],
    '5ed96bf2': [
        (log,                           ('1.3: Lighter BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('8899e0fd', 'Lighter.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('be46890b', 'Lighter.BodyA.Diffuse.1024')),
    ],
    'da6f4dc0': [
        (log,                           ('1.3: Lighter BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('8899e0fd', 'Lighter.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5b828635', 'Lighter.BodyA.LightMap.1024')),
    ],
    '94aebd7e': [
        (log,                           ('1.3: Lighter BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('8899e0fd', 'Lighter.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('65f3bb7c', 'Lighter.BodyA.MaterialMap.1024')),
    ],

    '6506987b': [
        (log,                           ('1.3: Lighter ArmA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('018b03f0', 'Lighter.Arm.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8b854866', 'Lighter.ArmA.Diffuse.2048')),
    ],
    '939a2e18': [
        (log,                           ('1.3: Lighter ArmA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('018b03f0', 'Lighter.Arm.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('547cbcd8', 'Lighter.ArmA.LightMap.2048')),
    ],
    '1684d3e4': [
        (log,                           ('1.3: Lighter ArmA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('018b03f0', 'Lighter.Arm.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3617c303', 'Lighter.ArmA.MaterialMap.2048')),
    ],
    '8b854866': [
        (log,                           ('1.3: Lighter ArmA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('018b03f0', 'Lighter.Arm.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6506987b', 'Lighter.ArmA.Diffuse.1024')),
    ],
    '547cbcd8': [
        (log,                           ('1.3: Lighter ArmA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('018b03f0', 'Lighter.Arm.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('939a2e18', 'Lighter.ArmA.LightMap.1024')),
    ],
    '3617c303': [
        (log,                           ('1.3: Lighter ArmA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('018b03f0', 'Lighter.Arm.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1684d3e4', 'Lighter.ArmA.MaterialMap.1024')),
    ],



    # MARK: Lucy
    '69ad9d08': [(log, ('1.3: Lucy Hair IB Hash',)),     (add_ib_check_if_missing,)],
    '272dd7f6': [(log, ('1.0: Lucy Snout IB Hash',)),    (add_ib_check_if_missing,)],
    '9b6370f6': [(log, ('1.0: Lucy Belt IB Hash',)),     (add_ib_check_if_missing,)],
    'be5f4c7d': [(log, ('1.3: Lucy Body IB Hash',)),     (add_ib_check_if_missing,)],
    '1fe6e084': [(log, ('1.0: Lucy RedCloth IB Hash',)), (add_ib_check_if_missing,)],
    'a0ed04de': [(log, ('1.0: Lucy Helmet IB Hash',)),   (add_ib_check_if_missing,)],
    'df3e3965': [(log, ('1.3: Lucy Face IB Hash',)),     (add_ib_check_if_missing,)],

    '5315f036': [(log, ('1.2 -> 1.3: Lucy Hair Blend Hash',)),    (update_hash, ('a37c7537',))],
    '751e21a5': [(log, ('1.2 -> 1.3: Lucy Hair Texcoord Hash',)), (update_hash, ('c8810832',))],
    '198e99d7': [
        (log, ('1.2 -> 1.3: Lucy Hair IB Hash',)),
        (update_hash, ('69ad9d08',)),
        (transfer_indexed_sections, {
            'src_indices': ['0', '-1'],
            'trg_indices': ['0', '5253'],
        })
    ],

    '5da9dafc': [(log, ('1.2 -> 1.3: Lucy Body Position Hash',)), (update_hash, ('246b93e2',))],
    'b94b02e8': [(log, ('1.2 -> 1.3: Lucy Body Blend Hash',)),    (update_hash, ('66948a0f',))],
    '00f11ea6': [(log, ('1.2 -> 1.3: Lucy Body Texcoord Hash',)), (update_hash, ('f60dbb9e',))],
    'e0ad50ed': [(log, ('1.2 -> 1.3: Lucy Body IB Hash',)),       (update_hash, ('be5f4c7d',))],

    'fca15ccb': [(log, ('1.2 -> 1.3: Lucy Face IB Hash',)),       (update_hash, ('df3e3965',))],


    '483b418a': [(log, ('1.2 -> 1.3: Lucy FaceA Diffuse 1024p Hash',)), (update_hash, ('2578d35b',))],
    '2a6df536': [(log, ('1.2 -> 1.3: Lucy FaceA Diffuse 1024p Hash',)), (update_hash, ('4e2d5baa',))],

    '2578d35b': [
        (log,                           ('1.3: Lucy FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('df3e3965', 'fca15ccb'), 'Lucy.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('4e2d5baa', '2a6df536'), 'Lucy.FaceA.Diffuse.2048')),
    ],
    '4e2d5baa': [
        (log,                           ('1.3: Lucy FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('df3e3965', 'fca15ccb'), 'Lucy.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('2578d35b', '483b418a'), 'Lucy.FaceA.Diffuse.1024')),
    ],


    'b50eb71c': [(log, ('1.2 -> 1.3: Lucy HairA, SnoutA, BeltA Diffuse 1024p Hash',)),     (update_hash, ('753baa45',))],
    'd1241cfc': [(log, ('1.2 -> 1.3: Lucy HairA, SnoutA, BeltA MaterialMap 1024p Hash',)), (update_hash, ('368f931c',))],

    'aa513afa': [(log, ('1.2 -> 1.3: Lucy HairA, SnoutA, BeltA Diffuse 2048p Hash',)),     (update_hash, ('0fa60fe1',))],
    '919b608c': [(log, ('1.2 -> 1.3: Lucy HairA, SnoutA, BeltA MaterialMap 2048p Hash',)), (update_hash, ('068aba7f',))],

    '0fa60fe1': [
        (log,                           ('1.3: Lucy HairA, SnoutA, BeltA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   (('753baa45', 'b50eb71c'), 'Lucy.HairA.Diffuse.1024')),
    ],
    '753baa45': [
        (log,                           ('1.3: Lucy HairA, SnoutA, BeltA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   (('0fa60fe1', 'aa513afa'), 'Lucy.HairA.Diffuse.2048')),
    ],
    '1a3b30ba': [
        (log,                           ('1.0: Lucy HairA, SnoutA, BeltA LightMap 2048p Hash',)),
        (multiply_section_if_missing,   ('810c0878', 'Lucy.HairA.LightMap.1024')),
    ],
    '810c0878': [
        (log,                           ('1.0: Lucy HairA, SnoutA, BeltA LightMap 1024p Hash',)),
        (multiply_section_if_missing,   ('1a3b30ba', 'Lucy.HairA.LightMap.2048')),
    ],
    '068aba7f': [
        (log,                           ('1.3: Lucy HairA, SnoutA, BeltA MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   (('368f931c', 'd1241cfc'), 'Lucy.HairA.MaterialMap.1024')),
    ],
    '368f931c': [
        (log,                           ('1.3: Lucy HairA, SnoutA, BeltA MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   (('068aba7f', '919b608c'), 'Lucy.HairA.MaterialMap.2048')),
    ],
    'edcb9661': [
        (log,                           ('1.0: Lucy HairA, SnoutA, BeltA NormalMap 2048p Hash',)),
        (multiply_section_if_missing,   ('9114c7c7', 'Lucy.HairA.NormalMap.1024')),
    ],
    '9114c7c7': [
        (log,                           ('1.0: Lucy HairA, SnoutA, BeltA NormalMap 1024p Hash',)),
        (multiply_section_if_missing,   ('edcb9661', 'Lucy.HairA.NormalMap.2048')),
    ],


    '474c7aa2': [
        (log,                           ('1.0: Lucy BodyA, RedClothA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   ('f810e7ac', 'Lucy.BodyA.Diffuse.1024')),
    ],
    'f810e7ac': [
        (log,                           ('1.0: Lucy BodyA, RedClothA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   ('474c7aa2', 'Lucy.BodyA.Diffuse.2048')),
    ],
    '855d9fa3': [
        (log,                           ('1.0: Lucy BodyA, RedClothA LightMap 2048p Hash',)),
        (multiply_section_if_missing,   ('e89f7814', 'Lucy.BodyA.LightMap.1024')),
    ],
    'e89f7814': [
        (log,                           ('1.0: Lucy BodyA, RedClothA LightMap 1024p Hash',)),
        (multiply_section_if_missing,   ('855d9fa3', 'Lucy.BodyA.LightMap.2048')),
    ],
    '1fd24fd8': [
        (log,                           ('1.0: Lucy BodyA, RedClothA MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   ('86ca6cfd', 'Lucy.BodyA.MaterialMap.1024')),
    ],
    '86ca6cfd': [
        (log,                           ('1.0: Lucy BodyA, RedClothA MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   ('1fd24fd8', 'Lucy.BodyA.MaterialMap.2048')),
    ],
    '463b4f55': [
        (log,                           ('1.0: Lucy BodyA, RedClothA NormalMap 2048p Hash',)),
        (multiply_section_if_missing,   ('1711cafd', 'Lucy.BodyA.NormalMap.1024')),
    ],
    '1711cafd': [
        (log,                           ('1.0: Lucy BodyA, RedClothA NormalMap 1024p Hash',)),
        (multiply_section_if_missing,   ('463b4f55', 'Lucy.BodyA.NormalMap.2048')),
    ],


    'b3013a33': [(log, ('1.0 -> 2.0: Lucy HelmetA MaterialMap 2048p Hash',)),       (update_hash, ('0a99d9d5',))],
    '4227db77': [(log, ('1.0 -> 2.0: Lucy HelmetA MaterialMap 1024p Hash',)),       (update_hash, ('2243086f',))],


    'a0be0ed3': [
        (log,                           ('1.0: Lucy HelmetA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('a0ed04de', 'Lucy.Helmet.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('919ab7e5', 'Lucy.HelmetA.Diffuse.1024')),
    ],
    '919ab7e5': [
        (log,                           ('1.0: Lucy HelmetA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('a0ed04de', 'Lucy.Helmet.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a0be0ed3', 'Lucy.HelmetA.Diffuse.2048')),
    ],
    '8d9a16c7': [
        (log,                           ('1.0: Lucy HelmetA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('a0ed04de', 'Lucy.Helmet.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6a8fca92', 'Lucy.HelmetA.LightMap.1024')),
    ],
    '6a8fca92': [
        (log,                           ('1.0: Lucy HelmetA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('a0ed04de', 'Lucy.Helmet.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8d9a16c7', 'Lucy.HelmetA.LightMap.2048')),
    ],
    '0a99d9d5': [
        (log,                           ('2.0: Lucy HelmetA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('a0ed04de', 'Lucy.Helmet.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('2243086f', '4227db77'), 'Lucy.HelmetA.MaterialMap.1024')),
    ],
    '2243086f': [
        (log,                           ('2.0: Lucy HelmetA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('a0ed04de', 'Lucy.Helmet.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('0a99d9d5', 'b3013a33'), 'Lucy.HelmetA.MaterialMap.2048')),
    ],
    'ca5fd23a': [
        (log,                           ('1.0: Lucy HelmetA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('a0ed04de', 'Lucy.Helmet.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f4d44970', 'Lucy.HelmetA.NormalMap.1024')),
    ],
    'f4d44970': [
        (log,                           ('1.0: Lucy HelmetA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('a0ed04de', 'Lucy.Helmet.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ca5fd23a', 'Lucy.HelmetA.NormalMap.2048')),
    ],



    # MARK: Lycaon
    '060bc1ad': [(log, ('1.0: Lycaon Hair IB Hash',)),              (add_ib_check_if_missing,)],
    '395572dc': [(log, ('1.3 -> 1.4: Lycaon Hair Texcoord Hash',)), (update_hash, ('b092c043',))],
    
    '25196b7a': [(log, ('1.3 -> 1.4: Lycaon Body IB Hash',)), (update_hash, ('6749b6e7',))],
    '6749b6e7': [(log, ('1.4: Lycaon Body IB Hash',)),        (add_ib_check_if_missing,)],
    
    '2a340ed5': [(log, ('1.3 -> 1.4: Lycaon Body Draw Hash',)),     (update_hash, ('25418598',))],
    '949e688a': [(log, ('1.3 -> 1.4: Lycaon Body Texcoord Hash',)), (update_hash, ('b950fda5',))],
    'b68056b4': [
        (log, ('1.3 -> 1.4: Lycaon Body Position Hash',)),
        (update_hash, ('8c7775ae',)),
        (log, ('1.3 -> 1.4: Lycaon Body Blend Remap',)),
        (update_buffer_blend_indices, (
            '8c7775ae',
            (50, 51, 89, 90,  98,  99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110),
            (51, 50, 90, 89, 669, 669, 669, 669, 669, 669, 669, 669, 669,  98,  99, 100, 101)
        ))
    ],
    'a485180e': [
        (log,                         ('1.3 -> 1.4: Lycaon Body Blend Remap',)),
        (update_hash,                 ('f2d1a929',)),
        (update_buffer_blend_indices, (
            'f2d1a929',
            (50, 51, 89, 90,  98,  99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110),
            (51, 50, 90, 89, 669, 669, 669, 669, 669, 669, 669, 669, 669,  98,  99, 100, 101)
        )),
    ],

    '5e710f36': [(log, ('1.0: Lycaon Mask IB Hash',)), (add_ib_check_if_missing,)],
    '22a1347b': [(log, ('1.0: Lycaon Legs IB Hash',)), (add_ib_check_if_missing,)],
    '6ffdfccb': [(log, ('1.6: Lycaon Face IB Hash',)), (add_ib_check_if_missing,)],

    '7074f97e': [(log, ('1.5 -> 1.6: Lycaon Face Draw Hash',)),     (update_hash, ('44277f65',))],
    '4a666a39': [(log, ('1.5 -> 1.6: Lycaon Face Position Hash',)), (update_hash, ('7e35ec22',))],
    'c862a611': [(log, ('1.5 -> 1.6: Lycaon Face Blend Hash',)),    (update_hash, ('e2d4c532',))],
    '6902f441': [(log, ('1.? -> 1.?: Lycaon Face Texcoord Hash',)), (update_hash, ('b1edaf35',))],
    'b1edaf35': [(log, ('1.? -> 1.6: Lycaon Face Texcoord Hash',)), (update_hash, ('3adaebb3',))],
    '7341e07b': [(log, ('1.5 -> 1.6: Lycaon Face IB Hash',)),       (update_hash, ('6ffdfccb',))],


    'd14f3284': [(log, ('1.5 -> 1.6: Lycaon FaceA Diffuse 2048p Hash',)), (update_hash, ('7077ebb1',))],
    '4f098897': [(log, ('1.5 -> 1.6: Lycaon Face Diffuse 1024p Hash',)), (update_hash, ('2cc208a7',))],


    '2cc208a7': [
        (log,                           ('1.6: Lycaon FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('6ffdfccb', '7341e07b'), 'Lycaon.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('7077ebb1', 'd14f3284'), 'Lycaon.FaceA.Diffuse.2048')),
    ],

    '7077ebb1': [
        (log,                           ('1.6: Lycaon FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('6ffdfccb', '7341e07b'), 'Lycaon.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('2cc208a7', '4f098897'), 'Lycaon.FaceA.Diffuse.1024')),
    ],


    '3d6eb388': [(log, ('1.3 -> 1.4: Lycaon HairA, MaskA LightMap 2048p Hash',)),   (update_hash, ('04d061fe',))],
    '4d4e8986': [(log, ('1.3 -> 1.4: Lycaon HairA, MaskA LightMap 1024p Hash',)),   (update_hash, ('4d878953',))],

    '04d061fe': [(log, ('1.4 -> 2.0: Lycaon HairA, MaskA LightMap 2048p Hash',)),   (update_hash, ('f7daa6d9',))],
    '4d878953': [(log, ('1.4 -> 2.0: Lycaon HairA, MaskA LightMap 1024p Hash',)),   (update_hash, ('7c129f48',))],


    '61aaace5': [
        (log,                           ('1.0: Lycaon HairA, MaskA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   ('3bd1b7e6', 'Lycaon.HairA.Diffuse.1024')),
    ],
    '3bd1b7e6': [
        (log,                           ('1.0: Lycaon HairA, MaskA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   ('61aaace5', 'Lycaon.HairA.Diffuse.2048')),
    ],
    'f7daa6d9': [
        (log,                           ('2.0: Lycaon HairA, MaskA LightMap 2048p Hash',)),
        (multiply_section_if_missing,   (('7c129f48', '4d4e8986', '4d878953'), 'Lycaon.HairA.LightMap.1024')),
    ],
    '7c129f48': [
        (log,                           ('2.0: Lycaon HairA, MaskA LightMap 1024p Hash',)),
        (multiply_section_if_missing,   (('f7daa6d9', '3d6eb388', '04d061fe'), 'Lycaon.HairA.LightMap.2048')),
    ],
    '02bfcc69': [
        (log,                           ('1.0: Lycaon HairA, MaskA MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   ('ba0f8320', 'Lycaon.HairA.MaterialMap.1024')),
    ],
    'ba0f8320': [
        (log,                           ('1.0: Lycaon HairA, MaskA MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   ('02bfcc69', 'Lycaon.HairA.MaterialMap.2048')),
    ],
    '5817e801': [
        (log,                           ('1.0: Lycaon HairA, MaskA NormalMap 2048p Hash',)),
        (multiply_section_if_missing,   ('71925b2f', 'Lycaon.HairA.NormalMap.1024')),
    ],
    '71925b2f': [
        (log,                           ('1.0: Lycaon HairA, MaskA NormalMap 1024p Hash',)),
        (multiply_section_if_missing,   ('5817e801', 'Lycaon.HairA.NormalMap.2048')),
    ],


    '565aa8be': [(log, ('1.3 -> 1.4: Lycaon Body LightMap 2048p Hash',)),           (update_hash, ('814db5bf',))],
    '7ea75154': [(log, ('1.3 -> 1.4: Lycaon Body LightMap 1024p Hash',)),           (update_hash, ('122c655e',))],

    '814db5bf': [(log, ('1.4 -> 2.0: Lycaon BodyA LightMap 2048p Hash',)),          (update_hash, ('fbf5a9b5',))],
    '122c655e': [(log, ('1.4 -> 2.0: Lycaon BodyA LightMap 1024p Hash',)),          (update_hash, ('391855b7',))],


    '7169ec86': [
        (log,                           ('1.0: Lycaon BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('6749b6e7', '25196b7a'), 'Lycaon.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('82ad0c28', 'Lycaon.BodyA.Diffuse.1024')),
    ],
    '82ad0c28': [
        (log,                           ('1.0: Lycaon BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('6749b6e7', '25196b7a'), 'Lycaon.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7169ec86', 'Lycaon.BodyA.Diffuse.2048')),
    ],
    'fbf5a9b5': [
        (log,                           ('2.0: Lycaon BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        (('6749b6e7', '25196b7a'), 'Lycaon.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('391855b7', '7ea75154', '122c655e'), 'Lycaon.BodyA.LightMap.1024')),
    ],
    '391855b7': [
        (log,                           ('2.0: Lycaon BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        (('6749b6e7', '25196b7a'), 'Lycaon.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('fbf5a9b5', '565aa8be', '814db5bf'), 'Lycaon.BodyA.LightMap.2048')),
    ],
    '5a321eae': [
        (log,                           ('1.0: Lycaon BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        (('6749b6e7', '25196b7a'), 'Lycaon.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7cca7d7e', 'Lycaon.BodyA.MaterialMap.1024')),
    ],
    '7cca7d7e': [
        (log,                           ('1.0: Lycaon BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        (('6749b6e7', '25196b7a'), 'Lycaon.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5a321eae', 'Lycaon.BodyA.MaterialMap.2048')),
    ],
    'c8fd1702': [
        (log,                           ('1.0: Lycaon BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        (('6749b6e7', '25196b7a'), 'Lycaon.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('bac2b2e2', 'Lycaon.BodyA.NormalMap.1024')),
    ],
    'bac2b2e2': [
        (log,                           ('1.0: Lycaon BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        (('6749b6e7', '25196b7a'), 'Lycaon.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c8fd1702', 'Lycaon.BodyA.NormalMap.2048')),
    ],


    '072e6786': [(log, ('1.0 -> 2.0: Lycaon LegsA LightMap 2048p Hash',)),              (update_hash, ('57b175c5',))],
    '3dfdab95': [(log, ('1.0 -> 2.0: Lycaon LegsA LightMap 1024p Hash',)),              (update_hash, ('9bcd5f77',))],
    '4a4ea6dc': [(log, ('1.0 -> 2.0: Lycaon LegsA MaterialMap 2048p Hash',)),           (update_hash, ('4b18f890',))],
    '288e7fbd': [(log, ('1.0 -> 2.0: Lycaon LegsA MaterialMap 1024p Hash',)),           (update_hash, ('b4e95c1d',))],


    'd947066b': [
        (log,                           ('1.0: Lycaon LegsA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('22a1347b', 'Lycaon.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('89bd4d58', 'Lycaon.LegsA.Diffuse.1024')),
    ],
    '89bd4d58': [
        (log,                           ('1.0: Lycaon LegsA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('22a1347b', 'Lycaon.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d947066b', 'Lycaon.LegsA.Diffuse.2048')),
    ],
    '57b175c5': [
        (log,                           ('2.0: Lycaon LegsA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('22a1347b', 'Lycaon.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('9bcd5f77', '3dfdab95'), 'Lycaon.LegsA.LightMap.1024')),
    ],
    '9bcd5f77': [
        (log,                           ('2.0: Lycaon LegsA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('22a1347b', 'Lycaon.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('57b175c5', '072e6786'), 'Lycaon.LegsA.LightMap.2048')),
    ],
    '4b18f890': [
        (log,                           ('2.0: Lycaon LegsA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('22a1347b', 'Lycaon.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('b4e95c1d', '288e7fbd'), 'Lycaon.LegsA.MaterialMap.1024')),
    ],
    'b4e95c1d': [
        (log,                           ('2.0: Lycaon LegsA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('22a1347b', 'Lycaon.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('4b18f890', '4a4ea6dc'), 'Lycaon.LegsA.MaterialMap.2048')),
    ],
    '72f53876': [
        (log,                           ('1.0: Lycaon LegsA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('22a1347b', 'Lycaon.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a6efc854', 'Lycaon.LegsA.NormalMap.1024')),
    ],
    'a6efc854': [
        (log,                           ('1.0: Lycaon LegsA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('22a1347b', 'Lycaon.Legs.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('72f53876', 'Lycaon.LegsA.NormalMap.2048')),
    ],



    # MARK: Miyabi
    '4faabaac': [(log, ('1.4: Miyabi Hair IB Hash',)),   (add_ib_check_if_missing,)],
    '981c1a1e': [(log, ('1.4: Miyabi Body IB Hash',)),   (add_ib_check_if_missing,)],
    'd8003df3': [(log, ('1.4: Miyabi Legs IB Hash',)),   (add_ib_check_if_missing,)],
    'dbd59d30': [(log, ('1.4: Miyabi Face IB Hash',)),   (add_ib_check_if_missing,)],


    '1d487fd5': [
        (log,                           ('1.4: Miyabi FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('dbd59d30', 'Miyabi.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('92599e94', 'Miyabi.FaceA.Diffuse.1024')),
    ],
    '92599e94': [
        (log,                           ('1.4: Miyabi FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('dbd59d30', 'Miyabi.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1d487fd5', 'Miyabi.FaceA.Diffuse.2048')),
    ],


    '012e84e9': [
        (log,                           ('1.4: Miyabi HairA, LegsA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   ('ed6b94f7', 'Miyabi.HairA.Diffuse.1024')),
    ],
    'ed6b94f7': [
        (log,                           ('1.4: Miyabi HairA, LegsA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   ('012e84e9', 'Miyabi.HairA.Diffuse.2048')),
    ],
    'a6ea6d83': [
        (log,                           ('1.4: Miyabi HairA, LegsA LightMap 2048p Hash',)),
        (multiply_section_if_missing,   ('8b5708f4', 'Miyabi.HairA.LightMap.1024')),
    ],
    '8b5708f4': [
        (log,                           ('1.4: Miyabi HairA, LegsA LightMap 1024p Hash',)),
        (multiply_section_if_missing,   ('a6ea6d83', 'Miyabi.HairA.LightMap.2048')),
    ],
    'd5462e37': [
        (log,                           ('1.4: Miyabi HairA, LegsA MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   ('a84d9003', 'Miyabi.HairA.MaterialMap.1024')),
    ],
    'a84d9003': [
        (log,                           ('1.4: Miyabi HairA, LegsA MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   ('d5462e37', 'Miyabi.HairA.MaterialMap.2048')),
    ],


    '09a2bbd1': [
        (log,                           ('1.4: Miyabi BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('981c1a1e', 'Miyabi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1a3644e7', 'Miyabi.BodyA.Diffuse.1024')),
    ],
    '1a3644e7': [
        (log,                           ('1.4: Miyabi BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('981c1a1e', 'Miyabi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('09a2bbd1', 'Miyabi.BodyA.Diffuse.2048')),
    ],
    'fd289380': [
        (log,                           ('1.4: Miyabi BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('981c1a1e', 'Miyabi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0492f64a', 'Miyabi.BodyA.LightMap.1024')),
    ],
    '0492f64a': [
        (log,                           ('1.4: Miyabi BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('981c1a1e', 'Miyabi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('fd289380', 'Miyabi.BodyA.LightMap.2048')),
    ],
    '450770fd': [
        (log,                           ('1.4: Miyabi BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('981c1a1e', 'Miyabi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('168b1df9', 'Miyabi.BodyA.MaterialMap.1024')),
    ],
    '168b1df9': [
        (log,                           ('1.4: Miyabi BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('981c1a1e', 'Miyabi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('450770fd', 'Miyabi.BodyA.MaterialMap.2048')),
    ],



    # MARK: Nekomata
    'da11fd85': [(log, ('1.0: Nekomata Hair IB Hash',)),   (add_ib_check_if_missing,)],
    '26a487ff': [(log, ('1.0: Nekomata Body IB Hash',)),   (add_ib_check_if_missing,)],
    '74688145': [(log, ('1.0: Nekomata Swords IB Hash',)), (add_ib_check_if_missing,)],
    '37119851': [(log, ('1.0: Nekomata Face IB Hash',)),   (add_ib_check_if_missing,)],

    '2c317dda': [(log, ('1.0 -> 1.1: Nekomata Body Position Hash',)),  (update_hash, ('eaad1408',))],
    'b5a4c084': [(log, ('1.0 -> 1.1: Nekomata Body Texcoord Hash',)),  (update_hash, ('f589a51f',))],

    '6abb714e': [(log, ('1.0 -> 1.1: Nekomata Swords Position Hash',)), (update_hash, ('3c4015fd',))],
    '70f4875e': [(log, ('1.0 -> 1.1: Nekomata Swords Texcoord Hash',)), (update_hash, ('2a4f8c9e',))],



    'fed3abbe': [(log, ('1.0 -> 1.1: Nekomata FaceA Diffuse 2048p Hash',)), (update_hash, ('ba411d22',))],
    'd9370c84': [(log, ('1.0 -> 1.1: Nekomata FaceA Diffuse 1024p Hash',)), (update_hash, ('0834f635',))],

    'ba411d22': [
        (log,                           ('1.1: Nekomata FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('37119851', 'Nekomata.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('0834f635', 'd9370c84'), 'Nekomata.FaceA.Diffuse.1024')),
    ],
    '0834f635': [
        (log,                           ('1.1: Nekomata FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('37119851', 'Nekomata.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('ba411d22', 'fed3abbe'), 'Nekomata.FaceA.Diffuse.2048')),
    ],


    '548c7f7d': [(log, ('1.0 -> 2.0: Nekomata HairA LightMap 2048p Hash',)),           (update_hash, ('1c0193dc',))],
    'f8accad8': [(log, ('1.0 -> 1.x: Nekomata HairA LightMap 1024p Hash',)),           (update_hash, ('0deeb9d2',))],
    '0deeb9d2': [(log, ('1.x -> 2.0: Nekomata HairA LightMap 1024p Hash',)),           (update_hash, ('362c205e',))],
    '4ca5efc6': [(log, ('1.0 -> 2.0: Nekomata HairA MaterialMap 2048p Hash',)),        (update_hash, ('3f73186f',))],
    '0c22352c': [(log, ('1.0 -> 1.x: Nekomata HairA MaterialMap 1024p Hash',)),        (update_hash, ('63687775',))],
    '63687775': [(log, ('1.x -> 2.0: Nekomata HairA MaterialMap 1024p Hash',)),        (update_hash, ('378b282c',))],

    '25f3ae9b': [
        (log,                           ('1.0: Nekomata HairA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   ('aed3d8bd', 'Nekomata.HairA.Diffuse.1024')),
    ],
    'aed3d8bd': [
        (log,                           ('1.0: Nekomata HairA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   ('25f3ae9b', 'Nekomata.HairA.Diffuse.2048')),
    ],
    '1c0193dc': [
        (log,                           ('2.0: Nekomata HairA LightMap 2048p Hash',)),
        (multiply_section_if_missing,   (('362c205e', '0deeb9d2', 'f8accad8'), 'Nekomata.HairA.LightMap.1024')),
    ],
    '362c205e': [
        (log,                           ('2.0: Nekomata HairA LightMap 1024p Hash',)),
        (multiply_section_if_missing,   (('1c0193dc', '548c7f7d'), 'Nekomata.HairA.LightMap.2048')),
    ],
    '3f73186f': [
        (log,                           ('2.0: Nekomata HairA MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   (('378b282c', '63687775', '0c22352c'), 'Nekomata.HairA.MaterialMap.1024')),
    ],
    '378b282c': [
        (log,                           ('2.0: Nekomata HairA MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   (('3f73186f', '4ca5efc6'), 'Nekomata.HairA.MaterialMap.2048')),
    ],
    '799eb07d': [
        (log,                           ('1.0: Nekomata HairA NormalMap 2048p Hash',)),
        (multiply_section_if_missing,   ('c936ea68', 'Nekomata.HairA.NormalMap.1024')),
    ],
    'c936ea68': [
        (log,                           ('1.0: Nekomata HairA NormalMap 1024p Hash',)),
        (multiply_section_if_missing,   ('799eb07d', 'Nekomata.HairA.NormalMap.2048')),
    ],


    'd3f67c0d': [
        (log,                           ('1.0: -> 1.1: Nekomata HairB, BodyA, SwordsA Diffuse 2048p Hash',)),
        (update_hash,                   ('207b8e63',)),
    ],
    '37d3154d': [
        (log,                           ('1.0: -> 1.1: Nekomata HairB, BodyA, SwordsA Diffuse 1024p Hash',)),
        (update_hash,                   ('60687646',)),
    ],
    'f26828bd': [
        (log,                           ('1.0 -> 1.1: Nekomata HairB, BodyA, SwordsA MaterialMap 2048p Hash',)),
        (update_hash,                   ('b3286755',)),
    ],
    '424da647': [
        (log,                           ('1.0 -> 1.1: Nekomata HairB, BodyA, SwordsA MaterialMap 1024p Hash',)),
        (update_hash,                   ('a5529690',)),
    ],

    'fc53fc6f': [
        (log,                           ('1.0 -> 2.0: Nekomata HairB, BodyA, SwordsA LightMap 2048p Hash',)),
        (update_hash,                   ('25df29e7',)),
    ],
    '4f3f7df0': [
        (log,                           ('1.0 -> 2.0: Nekomata HairB, BodyA, SwordsA LightMap 1024p Hash',)),
        (update_hash,                   ('4c09361d',)),
    ],

    '207b8e63': [
        (log,                           ('1.1: Nekomata HairB, BodyA, SwordsA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   (('60687646', '37d3154d'), 'Nekomata.HairB.Diffuse.1024')),
    ],
    '60687646': [
        (log,                           ('1.1 Nekomata HairB, BodyA, SwordsA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   (('207b8e63', 'd3f67c0d'), 'Nekomata.HairB.Diffuse.2048')),
    ],
    '25df29e7': [
        (log,                           ('2.0: Nekomata HairB, BodyA, SwordsA LightMap 2048p Hash',)),
        (multiply_section_if_missing,   (('4c09361d', '4f3f7df0'), 'Nekomata.HairB.LightMap.1024')),
    ],
    '4c09361d': [
        (log,                           ('2.0: Nekomata HairB, BodyA, SwordsA LightMap 1024p Hash',)),
        (multiply_section_if_missing,   (('25df29e7', 'fc53fc6f'), 'Nekomata.HairB.LightMap.2048')),
    ],
    'b3286755': [
        (log,                           ('1.1: Nekomata HairB, BodyA, SwordsA MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   (('a5529690', '424da647'), 'Nekomata.HairB.MaterialMap.1024')),
    ],
    'a5529690': [
        (log,                           ('1.1: Nekomata HairB, BodyA, SwordsA MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   (('b3286755', 'f26828bd'), 'Nekomata.HairB.MaterialMap.2048')),
    ],
    'ecaef71c': [
        (log,                           ('1.0: Nekomata HairB, BodyA, SwordsA NormalMap 2048p Hash',)),
        (multiply_section_if_missing,   ('c1933b38', 'Nekomata.HairB.NormalMap.1024')),
    ],
    'c1933b38': [
        (log,                           ('1.0: Nekomata HairB, BodyA, SwordsA NormalMap 1024p Hash',)),
        (multiply_section_if_missing,   ('ecaef71c', 'Nekomata.HairB.NormalMap.2048')),
    ],



    # MARK: Nicole
    '6847bbbd': [(log, ('1.0: Nicole Hair IB Hash',)),    (add_ib_check_if_missing,)],
    '5a4c1ef3': [(log, ('1.0: Nicole Body IB Hash',)),    (add_ib_check_if_missing,)],
    '7435fc0e': [(log, ('1.0: Nicole Face IB Hash',)),    (add_ib_check_if_missing,)],


    '6abd3dd3': [
        (log,                           ('1.0: Nicole FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('7435fc0e', 'Nicole.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d1e84a34', 'Nicole.FaceA.Diffuse.2048')),
    ],
    'd1e84a34': [
        (log,                           ('1.0: Nicole FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('7435fc0e', 'Nicole.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6abd3dd3', 'Nicole.FaceA.Diffuse.1024')),
    ],


    '1dfd9e16': [(log, ('1.0 -> 2.0: Nicole HairA LightMap 2048p Hash',)),      (update_hash, ('8c9c25d5',))],
    '9adc04ed': [(log, ('1.0 -> 2.0: Nicole HairA LightMap 1024p Hash',)),      (update_hash, ('f3c21e41',))],


    '6d3868f9': [
        (log,                           ('1.0: Nicole HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('6847bbbd', 'Nicole.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7a45adcd', 'Nicole.HairA.Diffuse.1024')),
    ],
    '7a45adcd': [
        (log,                           ('1.0: Nicole HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('6847bbbd', 'Nicole.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6d3868f9', 'Nicole.HairA.Diffuse.2048')),
    ],
    '8c9c25d5': [
        (log,                           ('2.0: Nicole HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('6847bbbd', 'Nicole.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('f3c21e41', '9adc04ed'), 'Nicole.HairA.LightMap.1024')),
    ],
    'f3c21e41': [
        (log,                           ('2.0: Nicole HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('6847bbbd', 'Nicole.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('8c9c25d5', '1dfd9e16'), 'Nicole.HairA.LightMap.2048')),
    ],
    'bffb4a66': [
        (log,                           ('1.0: Nicole HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('6847bbbd', 'Nicole.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b8db0209', 'Nicole.HairA.NormalMap.1024')),
    ],
    'b8db0209': [
        (log,                           ('1.0: Nicole HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('6847bbbd', 'Nicole.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('bffb4a66', 'Nicole.HairA.NormalMap.2048')),
    ],


    'f86ffe2c': [
        (log,                           ('1.0: Nicole BodyA, BangbooA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9ee9b402', 'Nicole.BodyA.Diffuse.1024')),
    ],
    '9ee9b402': [
        (log,                           ('1.0: Nicole BodyA, BangbooA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f86ffe2c', 'Nicole.BodyA.Diffuse.2048')),
    ],
    '80855e0f': [
        (log,                           ('1.0: Nicole BodyA, BangbooA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2b5aa784', 'Nicole.BodyA.LightMap.1024')),
    ],
    '2b5aa784': [
        (log,                           ('1.0: Nicole BodyA, BangbooA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('80855e0f', 'Nicole.BodyA.LightMap.2048')),
    ],
    '95cabef3': [
        (log,                           ('1.0: Nicole BodyA, BangbooA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('bb33129d', 'Nicole.BodyA.MaterialMap.1024')),
    ],
    'bb33129d': [
        (log,                           ('1.0: Nicole BodyA, BangbooA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('95cabef3', 'Nicole.BodyA.MaterialMap.2048')),
    ],
    '8cf23419': [
        (log,                           ('1.0: Nicole BodyA, BangbooA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('580df52d', 'Nicole.BodyA.NormalMap.1024')),
    ],
    '580df52d': [
        (log,                           ('1.0: Nicole BodyA, BangbooA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8cf23419', 'Nicole.BodyA.NormalMap.2048')),
    ],



    # MARK: NicoleSkin
    '6847bbbd': [(log, ('1.0: Nicole Hair IB Hash',)),    (add_ib_check_if_missing,)],
    '5a4c1ef3': [(log, ('1.0: Nicole Body IB Hash',)),    (add_ib_check_if_missing,)],


    '6d3868f9': [
        (log,                           ('1.0: Nicole HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('6847bbbd', 'Nicole.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7a45adcd', 'Nicole.HairA.Diffuse.1024')),
    ],
    '7a45adcd': [
        (log,                           ('1.0: Nicole HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('6847bbbd', 'Nicole.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6d3868f9', 'Nicole.HairA.Diffuse.2048')),
    ],
    '8c9c25d5': [
        (log,                           ('2.0: Nicole HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('6847bbbd', 'Nicole.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('f3c21e41', '9adc04ed'), 'Nicole.HairA.LightMap.1024')),
    ],
    'f3c21e41': [
        (log,                           ('2.0: Nicole HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('6847bbbd', 'Nicole.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('8c9c25d5', '1dfd9e16'), 'Nicole.HairA.LightMap.2048')),
    ],


    'f86ffe2c': [
        (log,                           ('1.0: Nicole BodyA, BangbooA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9ee9b402', 'Nicole.BodyA.Diffuse.1024')),
    ],
    '9ee9b402': [
        (log,                           ('1.0: Nicole BodyA, BangbooA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f86ffe2c', 'Nicole.BodyA.Diffuse.2048')),
    ],
    '80855e0f': [
        (log,                           ('1.0: Nicole BodyA, BangbooA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2b5aa784', 'Nicole.BodyA.LightMap.1024')),
    ],
    '2b5aa784': [
        (log,                           ('1.0: Nicole BodyA, BangbooA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('80855e0f', 'Nicole.BodyA.LightMap.2048')),
    ],
    '95cabef3': [
        (log,                           ('1.0: Nicole BodyA, BangbooA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('bb33129d', 'Nicole.BodyA.MaterialMap.1024')),
    ],
    'bb33129d': [
        (log,                           ('1.0: Nicole BodyA, BangbooA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('5a4c1ef3', 'Nicole.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('95cabef3', 'Nicole.BodyA.MaterialMap.2048')),
    ],



    # MARK: PanYinhu
    'cb1a6db9': [(log, ('2.0: PanYinhu Body IB Hash',)),    (add_ib_check_if_missing,)],
    'ebb6a59b': [(log, ('2.0: PanYinhu Face IB Hash',)),    (add_ib_check_if_missing,)],
    'ff7e9b40': [(log, ('2.0: PanYinhu Hat IB Hash',)),    (add_ib_check_if_missing,)],


    'ed361b8f': [
        (log,                           ('2.0: PanYinhu FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('ebb6a59b', 'PanYinhu.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('452a0918', 'PanYinhu.FaceA.Diffuse.1024')),
    ],
    '452a0918': [
        (log,                           ('2.0: PanYinhu FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('ebb6a59b', 'PanYinhu.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ed361b8f', 'PanYinhu.FaceA.Diffuse.2048')),
    ],


    'c0928025': [
        (log,                           ('2.0: PanYinhu BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('cb1a6db9', 'PanYinhu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b20c7e8b', 'PanYinhu.BodyA.Diffuse.1024')),
    ],
    'b20c7e8b': [
        (log,                           ('2.0: PanYinhu BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('cb1a6db9', 'PanYinhu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c0928025', 'PanYinhu.BodyA.Diffuse.2048')),
    ],
    '7d3c4c3d': [
        (log,                           ('2.0: PanYinhu BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('cb1a6db9', 'PanYinhu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7967c15f', 'PanYinhu.BodyA.LightMap.1024')),
    ],
    '7967c15f': [
        (log,                           ('2.0: PanYinhu BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('cb1a6db9', 'PanYinhu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7d3c4c3d', 'PanYinhu.BodyA.LightMap.2048')),
    ],
    '42fc25f0': [
        (log,                           ('2.0: PanYinhu BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('cb1a6db9', 'PanYinhu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2daeed33', 'PanYinhu.BodyA.MaterialMap.1024')),
    ],
    '2daeed33': [
        (log,                           ('2.0: PanYinhu BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('cb1a6db9', 'PanYinhu.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('42fc25f0', 'PanYinhu.BodyA.MaterialMap.2048')),
    ],


    'f2433e17': [
        (log,                           ('2.0: PanYinhu HatA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('ff7e9b40', 'PanYinhu.Hat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('cf6afa84', 'PanYinhu.HatA.Diffuse.1024')),
    ],
    'cf6afa84': [
        (log,                           ('2.0: PanYinhu HatA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('ff7e9b40', 'PanYinhu.Hat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f2433e17', 'PanYinhu.HatA.Diffuse.2048')),
    ],
    'ddeaa4c3': [
        (log,                           ('2.0: PanYinhu HatA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('ff7e9b40', 'PanYinhu.Hat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('26454e30', 'PanYinhu.HatA.LightMap.1024')),
    ],
    '26454e30': [
        (log,                           ('2.0: PanYinhu HatA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('ff7e9b40', 'PanYinhu.Hat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ddeaa4c3', 'PanYinhu.HatA.LightMap.2048')),
    ],
    'de553410': [
        (log,                           ('2.0: PanYinhu HatA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('ff7e9b40', 'PanYinhu.Hat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e0433c18', 'PanYinhu.HatA.MaterialMap.1024')),
    ],
    'e0433c18': [
        (log,                           ('2.0: PanYinhu HatA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('ff7e9b40', 'PanYinhu.Hat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('de553410', 'PanYinhu.HatA.MaterialMap.2048')),
    ],



    # MARK: Piper
    '940454ef': [(log, ('1.0: Piper Hair IB Hash',)), (add_ib_check_if_missing,)],
    '585da98b': [(log, ('1.0: Piper Body IB Hash',)), (add_ib_check_if_missing,)],
    'e11baad9': [(log, ('1.0: Piper Face IB Hash',)), (add_ib_check_if_missing,)],
    
     # Reverted in 1.2
    # '8b6b17f8': [
    #     (log, ('1.0: -> 1.1: Piper Hair Texcoord Hash',)),
    #     (update_hash, ('fd1b9c29',)),
    #     (log, ('+ Remapping texcoord buffer from stride 20 to 32',)),
    #     (update_buffer_element_width, (('BBBB', 'ee', 'ff', 'ee'), ('ffff', 'ee', 'ff', 'ee'), '1.1')),
    #     (log, ('+ Setting texcoord vcolor alpha to 1',)),
    #     (update_buffer_element_value, (('ffff', 'ee', 'ff', 'ee'), ('xxx1', 'xx', 'xx', 'xx'), '1.1'))
    # ],

    'fd1b9c29': [
        (log, ('1.1 -> 1.2: Piper Hair Texcoord Hash',)),
        (update_hash, ('8b6b17f8',)),
        (log, ('+ Remapping texcoord buffer',)),
        (zzz_12_shrink_texcoord_color, ('1.2',))
    ],
    '8b6b17f8': [(log, ('1.3 -> 1.4: Piper Hair Texcoord Hash',)), (update_hash, ('1c6d41af',)),],

    'b2f3e6aa': [(log, ('1.1 -> 1.2: Piper Body Position Hash',)), (update_hash, ('ffe8fea7',)),],
    'a0d146b3': [(log, ('1.1 -> 1.2: Piper Body Texcoord Hash',)), (update_hash, ('a011f94e',)),],
    'a011f94e': [(log, ('1.2 -> 1.3: Piper Body Texcoord Hash',)), (update_hash, ('6357b120',)),],
    '764276de': [(log, ('1.2 -> 1.3: Piper Body Blend Hash',)),    (update_hash, ('3d329807',)),],


    '97a7862e': [(log, ('1.1 -> 1.2: Piper FaceA Diffuse 2048p Hash',)),   (update_hash, ('3b2eb1d9',))],
    '4b06ffe6': [(log, ('1.1 -> 1.2: Piper FaceA Diffuse 1024p Hash',)),   (update_hash, ('f1c8f946',))],

    '3b2eb1d9': [
        (log,                           ('1.2: Piper FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('e11baad9', 'Piper.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('f1c8f946', '4b06ffe6'), 'Piper.FaceA.Diffuse.1024')),
    ],
    'f1c8f946': [
        (log,                           ('1.2: Piper FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('e11baad9', 'Piper.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('3b2eb1d9', '97a7862e'), 'Piper.FaceA.Diffuse.2048')),
    ],


    '79953d32': [(log, ('1.0 -> 2.0: Piper Hair LightMap 2048p Hash',)),   (update_hash, ('1146c5c3',))],
    '92acb4d4': [(log, ('1.0 -> 2.0: Piper Hair LightMap 1024p Hash',)),   (update_hash, ('6bd15459',))],

    '69ed4d11': [
        (log,                           ('1.0: Piper HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('940454ef', 'Piper.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9b743eab', 'Piper.HairA.Diffuse.1024')),
    ],
    '9b743eab': [
        (log,                           ('1.0: Piper HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('940454ef', 'Piper.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('69ed4d11', 'Piper.HairA.Diffuse.2048')),
    ],
    '1146c5c3': [
        (log,                           ('2.0: Piper HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('940454ef', 'Piper.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('6bd15459', '92acb4d4'), 'Piper.HairA.LightMap.1024')),
    ],
    '6bd15459': [
        (log,                           ('2.0: Piper HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('940454ef', 'Piper.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('1146c5c3', '79953d32'), 'Piper.HairA.LightMap.2048')),
    ],
    'b3034dff': [
        (log,                           ('1.0: Piper HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('940454ef', 'Piper.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('78c42c66', 'Piper.HairA.MaterialMap.1024')),
    ],
    '78c42c66': [
        (log,                           ('1.0: Piper HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('940454ef', 'Piper.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b3034dff', 'Piper.HairA.MaterialMap.2048')),
    ],
    '7ca957d8': [
        (log,                           ('1.0: Piper HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('940454ef', 'Piper.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('db7dccbf', 'Piper.HairA.NormalMap.1024')),
    ],
    'db7dccbf': [
        (log,                           ('1.0: Piper HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('940454ef', 'Piper.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7ca957d8', 'Piper.HairA.NormalMap.2048')),
    ],


    'b4b74e7e': [(log, ('1.2 -> 1.3: Piper BodyA Diffuse 2048p Hash',)), (update_hash, ('fed40302',))],
    '621564e5': [(log, ('1.2 -> 1.3: Piper BodyA Diffuse 1024p Hash',)), (update_hash, ('b450949d',))],

    '9cc2aaa0': [(log, ('1.3 -> 2.0: Piper BodyA LightMap 2048p Hash',)), (update_hash, ('a32c39b9',))],
    'db9c7abf': [(log, ('1.3 -> 2.0: Piper BodyA LightMap 1024p Hash',)), (update_hash, ('7a281673',))],

    'fed40302': [
        (log,                           ('1.3: Piper BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('585da98b', 'Piper.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('b450949d', '621564e5'), 'Piper.BodyA.Diffuse.1024')),
    ],
    'b450949d': [
        (log,                           ('1.3: Piper BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('585da98b', 'Piper.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('fed40302', 'b4b74e7e'), 'Piper.BodyA.Diffuse.2048')),
    ],
    'a32c39b9': [
        (log,                           ('2.0: Piper BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('585da98b', 'Piper.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('7a281673', 'db9c7abf'), 'Piper.BodyA.LightMap.1024')),
    ],
    '7a281673': [
        (log,                           ('2.0: Piper BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('585da98b', 'Piper.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('a32c39b9', '9cc2aaa0'), 'Piper.BodyA.LightMap.2048')),
    ],
    '7fdee30d': [
        (log,                           ('1.0: Piper BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('585da98b', 'Piper.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('73e72a1e', 'Piper.BodyA.MaterialMap.1024')),
    ],
    '73e72a1e': [
        (log,                           ('1.0: Piper BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('585da98b', 'Piper.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7fdee30d', 'Piper.BodyA.MaterialMap.2048')),
    ],
    '51f1ec36': [
        (log,                           ('1.0: Piper BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('585da98b', 'Piper.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('73a61e88', 'Piper.BodyA.NormalMap.1024')),
    ],
    '73a61e88': [
        (log,                           ('1.0: Piper BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('585da98b', 'Piper.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('51f1ec36', 'Piper.BodyA.NormalMap.2048')),
    ],



    # MARK: Pulchra
    'bd385763': [(log, ('1.6: Pulchra Hair Body IB Hash',)), (add_ib_check_if_missing,)],
    '5b30f4da': [(log, ('1.6: Pulchra Mask IB Hash',)), (add_ib_check_if_missing,)],
    '62de5837': [(log, ('1.6: Pulchra Face IB Hash',)), (add_ib_check_if_missing,)],

    # Face
    '1626aafe': [
        (log,                           ('1.6: Pulchra FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('62de5837', 'Pulchra.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('32f923f1', 'Pulchra.FaceA.Diffuse.1024')),
    ],
    '32f923f1': [
        (log,                           ('1.6: Pulchra FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('62de5837', 'Pulchra.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1626aafe', 'Pulchra.FaceA.Diffuse.2048')),
    ],

    # Hair
    '57be79d6': [
        (log,                           ('1.6: Pulchra HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('fb0a816a', 'Pulchra.HairA.Diffuse.1024')),
    ],
    'fb0a816a': [
        (log,                           ('1.6: Pulchra HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('57be79d6', 'Pulchra.HairA.Diffuse.2048')),
    ],
    '12c44063': [
        (log,                           ('1.6: Pulchra HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f475e822', 'Pulchra.HairA.LightMap.1024')),
    ],
    'f475e822': [
        (log,                           ('1.6: Pulchra HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('12c44063', 'Pulchra.HairA.LightMap.2048')),
    ],
    'a553df20': [
        (log,                           ('1.6: Pulchra HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('64d75415', 'Pulchra.HairA.MaterialMap.1024')),
    ],
    '64d75415': [
        (log,                           ('1.6: Pulchra HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a553df20', 'Pulchra.HairA.MaterialMap.2048')),
    ],

    # Body
    '7fc03353': [
        (log,                           ('1.6: Pulchra BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('bf7eba0f', 'Pulchra.BodyA.Diffuse.1024')),
    ],
    'bf7eba0f': [
        (log,                           ('1.6: Pulchra BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7fc03353', 'Pulchra.BodyA.Diffuse.2048')),
    ],
    'd8462af0': [
        (log,                           ('1.6: Pulchra BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('47040200', 'Pulchra.BodyA.LightMap.1024')),
    ],
    '47040200': [
        (log,                           ('1.6: Pulchra BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d8462af0', 'Pulchra.BodyA.LightMap.2048')),
    ],
    'd404b789': [
        (log,                           ('1.6: Pulchra BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a66a11d0', 'Pulchra.BodyA.MaterialMap.1024')),
    ],
    'a66a11d0': [
        (log,                           ('1.6: Pulchra BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('bd385763', 'Pulchra.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d404b789', 'Pulchra.BodyA.MaterialMap.2048')),
    ],



    # MARK: Qingyi
    'f6e96452': [(log, ('1.1: Qingyi Face IB Hash',)), (add_ib_check_if_missing,)],
    '3cacba0a': [(log, ('1.1: Qingyi Hair IB Hash',)), (add_ib_check_if_missing,)],
    '195857d8': [(log, ('1.1: Qingyi Body IB Hash',)), (add_ib_check_if_missing,)],

    '0b75cd32': [
        (log,                           ('1.1: Qingyi FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('f6e96452', 'Qingyi.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a58b5444', 'Qingyi.FaceA.Diffuse.1024')),
    ],
    'a58b5444': [
        (log,                           ('1.1: Qingyi FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('f6e96452', 'Qingyi.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0b75cd32', 'Qingyi.FaceA.Diffuse.2048')),
    ],

    '0643440c': [
        (log, ('1.1 -> 1.2: Qingyi Hair Texcoord Hash',)),
        (update_hash, ('53a2b66e',)),
        (log, ('+ Remapping texcoord buffer',)),
        (zzz_12_shrink_texcoord_color, ('1.2',))
    ],

    '3212a0ca': [
        (log,                           ('1.1: Qingyi HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('3cacba0a', 'Qingyi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a472db9a', 'Qingyi.HairA.Diffuse.1024')),
    ],
    '2910fbd0': [
        (log,                           ('1.1: Qingyi HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('3cacba0a', 'Qingyi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('fc1847a9', 'Qingyi.HairA.NormalMap.1024')),
    ],
    '6e3ac847': [
        (log,                           ('1.1: Qingyi HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('3cacba0a', 'Qingyi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('683414c1', 'Qingyi.HairA.LightMap.1024')),
    ],
    '4a77fd3b': [
        (log,                           ('1.1: Qingyi HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('3cacba0a', 'Qingyi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('bfefa200', 'Qingyi.HairA.MaterialMap.1024')),
    ],
    'a472db9a': [
        (log,                           ('1.1: Qingyi HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('3cacba0a', 'Qingyi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3212a0ca', 'Qingyi.HairA.Diffuse.2048')),
    ],
    'fc1847a9': [
        (log,                           ('1.1: Qingyi HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('3cacba0a', 'Qingyi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2910fbd0', 'Qingyi.HairA.NormalMap.2048')),
    ],
    '683414c1': [
        (log,                           ('1.1: Qingyi HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('3cacba0a', 'Qingyi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6e3ac847', 'Qingyi.HairA.LightMap.2048')),
    ],
    'bfefa200': [
        (log,                           ('1.1: Qingyi HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('3cacba0a', 'Qingyi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4a77fd3b', 'Qingyi.HairA.MaterialMap.2048')),
    ],
    '1fa7e18e': [
        (log,                           ('1.1: Qingyi BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('195857d8', 'Qingyi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('aa3c1147', 'Qingyi.BodyA.Diffuse.1024')),
    ],
    '542c6b04': [
        (log,                           ('1.1: Qingyi BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('195857d8', 'Qingyi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4fbf05be', 'Qingyi.BodyA.NormalMap.1024')),
    ],
    '35c2a022': [
        (log,                           ('1.1: Qingyi BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('195857d8', 'Qingyi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4a484257', 'Qingyi.BodyA.LightMap.1024')),
    ],
    '41054bb6': [
        (log,                           ('1.1: Qingyi BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('195857d8', 'Qingyi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4e561ee5', 'Qingyi.BodyA.MaterialMap.1024')),
    ],
    'aa3c1147': [
        (log,                           ('1.1: Qingyi BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('195857d8', 'Qingyi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1fa7e18e', 'Qingyi.BodyA.Diffuse.2048')),
    ],
    '4fbf05be': [
        (log,                           ('1.1: Qingyi BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('195857d8', 'Qingyi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('542c6b04', 'Qingyi.BodyA.NormalMap.2048')),
    ],
    '4a484257': [
        (log,                           ('1.1: Qingyi BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('195857d8', 'Qingyi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('35c2a022', 'Qingyi.BodyA.LightMap.2048')),
    ],
    '4e561ee5': [
        (log,                           ('1.1: Qingyi BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('195857d8', 'Qingyi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('41054bb6', 'Qingyi.BodyA.MaterialMap.2048')),
    ],



    # MARK: Rina
    'cdb2cc7d': [(log, ('1.0: Rina Hair IB Hash',)), (add_ib_check_if_missing,)],
    '2825da1e': [(log, ('1.0: Rina Body IB Hash',)), (add_ib_check_if_missing,)],
    '9f90cfaa': [(log, ('1.0: Rina Face IB Hash',)), (add_ib_check_if_missing,)],


    '7ecc44ce': [
        (log,                           ('1.0: Rina FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('9f90cfaa', 'Rina.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('802a3281', 'Rina.FaceA.Diffuse.2048')),
    ],
    '802a3281': [
        (log,                           ('1.0: Rina FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('9f90cfaa', 'Rina.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7ecc44ce', 'Rina.FaceA.Diffuse.1024')),
    ],


    'eb5d9d1c': [
        (log,                           ('1.0: Rina HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('cdb2cc7d', 'Rina.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4b005a79', 'Rina.HairA.Diffuse.1024')),
    ],
    '4b005a79': [
        (log,                           ('1.0: Rina HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('cdb2cc7d', 'Rina.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('eb5d9d1c', 'Rina.HairA.Diffuse.2048')),
    ],
    '1145d2b8': [
        (log,                           ('1.0: Rina HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('cdb2cc7d', 'Rina.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('fb61499f', 'Rina.HairA.LightMap.1024')),
    ],
    'fb61499f': [
        (log,                           ('1.0: Rina HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('cdb2cc7d', 'Rina.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1145d2b8', 'Rina.HairA.LightMap.2048')),
    ],
    '82153e28': [
        (log,                           ('1.0: Rina HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('cdb2cc7d', 'Rina.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ea08fd96', 'Rina.HairA.MaterialMap.1024')),
    ],
    'ea08fd96': [
        (log,                           ('1.0: Rina HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('cdb2cc7d', 'Rina.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('82153e28', 'Rina.HairA.MaterialMap.2048')),
    ],
    '83ac7993': [
        (log,                           ('1.0: Rina HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('cdb2cc7d', 'Rina.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('fa3c40e9', 'Rina.HairA.NormalMap.1024')),
    ],
    'fa3c40e9': [
        (log,                           ('1.0: Rina HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('cdb2cc7d', 'Rina.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('83ac7993', 'Rina.HairA.NormalMap.2048')),
    ],


    'bf44bf67': [
        (log,                           ('1.0: Rina BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('2825da1e', 'Rina.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a23e2e14', 'Rina.BodyA.Diffuse.1024')),
    ],
    'a23e2e14': [
        (log,                           ('1.0: Rina BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('2825da1e', 'Rina.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('bf44bf67', 'Rina.BodyA.Diffuse.2048')),
    ],
    '95f4e9c8': [
        (log,                           ('1.0: Rina BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('2825da1e', 'Rina.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('fad76987', 'Rina.BodyA.LightMap.1024')),
    ],
    'fad76987': [
        (log,                           ('1.0: Rina BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('2825da1e', 'Rina.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('95f4e9c8', 'Rina.BodyA.LightMap.2048')),
    ],
    'ed47722f': [
        (log,                           ('1.0: Rina BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('2825da1e', 'Rina.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9fa6dfd3', 'Rina.BodyA.MaterialMap.1024')),
    ],
    '9fa6dfd3': [
        (log,                           ('1.0: Rina BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('2825da1e', 'Rina.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ed47722f', 'Rina.BodyA.MaterialMap.2048')),
    ],
    '97637a8f': [
        (log,                           ('1.0: Rina BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('2825da1e', 'Rina.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d6b20159', 'Rina.BodyA.NormalMap.1024')),
    ],
    'd6b20159': [
        (log,                           ('1.0: Rina BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('2825da1e', 'Rina.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('97637a8f', 'Rina.BodyA.NormalMap.2048')),
    ],



    # MARK: Seth
    '35cf83ad': [(log, ('1.1: Seth Hair IB Hash',)), (add_ib_check_if_missing,)],
    '00172ec3': [(log, ('1.1: Seth Body IB Hash',)), (add_ib_check_if_missing,)],
    '52f5aa74': [(log, ('1.1: Seth Face IB Hash',)), (add_ib_check_if_missing,)],

    # Reversed in v1.4
    # 'a91eeef2': [
    #     (log,            ('1.2 -> 1.3: Seth Hair Texcoord Hash',)),
    #     (update_hash,    ('a72f760f',)),
    #     (log,            ('+ Remapping texcoord buffer',)),
    #     (zzz_13_remap_texcoord, (
    #         '13_Seth_Hair',
    #         ('4B','2e','2f','2e'),
    #         ('4f','2e','2f','2e')
    #     )),
    # ],
    'a72f760f': [
        (log,            ('1.3 -> 1.4: Seth Hair Texcoord Hash',)),
        (update_hash,    ('a91eeef2',)),
        (log,            ('+ Remapping texcoord buffer',)),
        (zzz_13_remap_texcoord, (
            '14_Seth_Hair',
            ('4f','2e','2f','2e'),
            ('4B','2e','2f','2e')
        )),
    ],


    '09981aff': [
        (log,                           ('1.1: Seth FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('52f5aa74', 'Seth.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('fe5b7534', 'Seth.FaceA.Diffuse.1024')),
    ],
    'fe5b7534': [
        (log,                           ('1.1: Seth FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('52f5aa74', 'Seth.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('09981aff', 'Seth.FaceA.Diffuse.2048')),
    ],


    'd4de9ec1': [(log, ('1.1 -> 2.0: Seth HairA LightMap 2048p Hash',)),        (update_hash, ('a855884d',))],
    'c01dbf6c': [(log, ('1.1 -> 2.0: Seth HairA LightMap 1024p Hash',)),        (update_hash, ('ca070fa7',))],


    'dc8e244d': [
        (log,                           ('1.1: Seth HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('35cf83ad', 'Seth.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d3756c37', 'Seth.HairA.Diffuse.1024')),
    ],
    'd3756c37': [
        (log,                           ('1.1: Seth HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('35cf83ad', 'Seth.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('dc8e244d', 'Seth.HairA.Diffuse.2048')),
    ],
    'a855884d': [
        (log,                           ('2.0: Seth HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('35cf83ad', 'Seth.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('ca070fa7', 'c01dbf6c'), 'Seth.HairA.LightMap.1024')),
    ],
    'ca070fa7': [
        (log,                           ('2.0: Seth HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('35cf83ad', 'Seth.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('a855884d', 'd4de9ec1'), 'Seth.HairA.LightMap.2048')),
    ],
    '3c256565': [
        (log,                           ('1.1: Seth HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('35cf83ad', 'Seth.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('833e9405', 'Seth.HairA.MaterialMap.1024')),
    ],
    '833e9405': [
        (log,                           ('1.1: Seth HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('35cf83ad', 'Seth.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3c256565', 'Seth.HairA.MaterialMap.2048')),
    ],
    '3376b58c': [
        (log,                           ('1.1: Seth HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('35cf83ad', 'Seth.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('24d52dd8', 'Seth.HairA.NormalMap.1024')),
    ],
    '24d52dd8': [
        (log,                           ('1.1: Seth HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('35cf83ad', 'Seth.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3376b58c', 'Seth.HairA.NormalMap.2048')),
    ],


    '3d97c2ef': [(log, ('1.1 -> 2.0: Seth BodyA LightMap 2048p Hash',)),        (update_hash, ('5b205468',))],
    '9436aa83': [(log, ('1.1 -> 2.0: Seth BodyA LightMap 1024p Hash',)),        (update_hash, ('57cf813c',))],


    '7f8416ab': [
        (log,                           ('1.1: Seth BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('00172ec3', 'Seth.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('dbc90150', 'Seth.BodyA.Diffuse.1024')),
    ],
    'dbc90150': [
        (log,                           ('1.1: Seth BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('00172ec3', 'Seth.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7f8416ab', 'Seth.BodyA.Diffuse.2048')),
    ],
    '5b205468': [
        (log,                           ('2.0: Seth BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('00172ec3', 'Seth.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('57cf813c', '9436aa83'), 'Seth.BodyA.LightMap.1024')),
    ],
    '57cf813c': [
        (log,                           ('2.0: Seth BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('00172ec3', 'Seth.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('5b205468', '3d97c2ef'), 'Seth.BodyA.LightMap.2048')),
    ],
    '732d3f81': [
        (log,                           ('1.1: Seth BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('00172ec3', 'Seth.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('56775fcb', 'Seth.BodyA.MaterialMap.1024')),
    ],
    '56775fcb': [
        (log,                           ('1.1: Seth BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('00172ec3', 'Seth.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('732d3f81', 'Seth.BodyA.MaterialMap.2048')),
    ],
    'dde45d3d': [
        (log,                           ('1.1: Seth BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('00172ec3', 'Seth.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('62b047c5', 'Seth.BodyA.NormalMap.1024')),
    ],
    '62b047c5': [
        (log,                           ('1.1: Seth BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('00172ec3', 'Seth.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('dde45d3d', 'Seth.BodyA.NormalMap.2048')),
    ],



    # MARK: Soldier0
    '217ec790': [(log, ('1.6: Soldier0 Hair IB Hash',)), (add_ib_check_if_missing,)],
    '53d3f4e5': [(log, ('1.6: Soldier0 Body IB Hash',)), (add_ib_check_if_missing,)],
    'e30ca87f': [(log, ('2.0: Soldier0 Face IB Hash',)), (add_ib_check_if_missing,)],

    'f2f539b8': [(log, ('1.6 - 2.0: Soldier0 Face IB Hash',)), (update_hash, ('e30ca87f',))],


    '05d7b504': [
        (log,                           ('1.6: Soldier0 FaceA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   ('692c6d2b', 'Soldier0.FaceA.Diffuse.1024')),
    ],
    '692c6d2b': [
        (log,                           ('1.6: Soldier0 FaceA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   ('05d7b504', 'Soldier0.FaceA.Diffuse.2048')),
    ],


    '464847b3': [(log, ('1.6 - 2.0: Soldier0 HairA MaterialMap 2048p Hash',)), (update_hash, ('0b059f91',))],
    'ce3e73be': [(log, ('1.6 - 2.0: Soldier0 HairA MaterialMap 1024p Hash',)), (update_hash, ('bb979f59',))],


    'aa3d57ff': [
        (log,                           ('1.6: Soldier0 HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('217ec790', 'Soldier0.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8cb4086a', 'Soldier0.HairA.Diffuse.1024')),
    ],
    '8cb4086a': [
        (log,                           ('1.6: Soldier0 HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('217ec790', 'Soldier0.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('aa3d57ff', 'Soldier0.HairA.Diffuse.2048')),
    ],
    '8d42a55b': [
        (log,                           ('1.6: Soldier0 HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('217ec790', 'Soldier0.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('96a28554', 'Soldier0.HairA.LightMap.1024')),
    ],
    '96a28554': [
        (log,                           ('1.6: Soldier0 HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('217ec790', 'Soldier0.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8d42a55b', 'Soldier0.HairA.LightMap.2048')),
    ],
    '0b059f91': [
        (log,                           ('2.0: Soldier0 HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('217ec790', 'Soldier0.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('bb979f59', 'ce3e73be'), 'Soldier0.HairA.MaterialMap.1024')),
    ],
    'bb979f59': [
        (log,                           ('2.0: Soldier0 HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('217ec790', 'Soldier0.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('0b059f91', '464847b3'), 'Soldier0.HairA.MaterialMap.2048')),
    ],


    '627baf3f': [
        (log,                           ('1.6: Soldier0 BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('53d3f4e5', 'Soldier0.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0acef326', 'Soldier0.BodyA.Diffuse.1024')),
    ],
    '0acef326': [
        (log,                           ('1.6: Soldier0 BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('53d3f4e5', 'Soldier0.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('627baf3f', 'Soldier0.BodyA.Diffuse.2048')),
    ],
    '3a56b70b': [
        (log,                           ('1.6: Soldier0 BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('53d3f4e5', 'Soldier0.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('625ad0eb', 'Soldier0.BodyA.LightMap.1024')),
    ],
    '625ad0eb': [
        (log,                           ('1.6: Soldier0 BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('53d3f4e5', 'Soldier0.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3a56b70b', 'Soldier0.BodyA.LightMap.2048')),
    ],
    '7cfa12b6': [
        (log,                           ('1.6: Soldier0 BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('53d3f4e5', 'Soldier0.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('dea3c5a0', 'Soldier0.BodyA.MaterialMap.1024')),
    ],
    'dea3c5a0': [
        (log,                           ('1.6: Soldier0 BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('53d3f4e5', 'Soldier0.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7cfa12b6', 'Soldier0.BodyA.MaterialMap.2048')),
    ],



    # MARK: Soldier11
    '2fa74e2f': [(log, ('1.0: Soldier11 Hair IB Hash',)), (add_ib_check_if_missing,)],
    'e3ee72d9': [(log, ('1.0: Soldier11 Body IB Hash',)), (add_ib_check_if_missing,)],
    'bb315c43': [(log, ('1.0: Soldier11 Face IB Hash',)), (add_ib_check_if_missing,)],


    '3c8697e8': [
        (log,                           ('1.0: Soldier11 FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('bb315c43', 'Soldier11.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('67821d9d', 'Soldier11.FaceA.Diffuse.2048')),
    ],
    '67821d9d': [
        (log,                           ('1.0: Soldier11 FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('bb315c43', 'Soldier11.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3c8697e8', 'Soldier11.FaceA.Diffuse.1024')),
    ],


    '787659b9': [(log, ('1.0 - 2.0: Soldier11 HairA LightMap 2048p Hash',)), (update_hash, ('71993491',))],
    'baa3c836': [(log, ('1.0 - 2.0: Soldier11 HairA LightMap 1024p Hash',)), (update_hash, ('17e75c76',))],


    'b41b671a': [
        (log,                           ('1.0: Soldier11 HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('2fa74e2f', 'Soldier11.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('15f933dc', 'Soldier11.HairA.Diffuse.1024')),
    ],
    '15f933dc': [
        (log,                           ('1.0: Soldier11 HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('2fa74e2f', 'Soldier11.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b41b671a', 'Soldier11.HairA.Diffuse.2048')),
    ],
    '71993491': [
        (log,                           ('2.0: Soldier11 HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('2fa74e2f', 'Soldier11.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('17e75c76', 'baa3c836'), 'Soldier11.HairA.LightMap.1024')),
    ],
    '17e75c76': [
        (log,                           ('2.0: Soldier11 HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('2fa74e2f', 'Soldier11.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('71993491', '787659b9'), 'Soldier11.HairA.LightMap.2048')),
    ],
    '68d9644a': [
        (log,                           ('1.0: Soldier11 HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('2fa74e2f', 'Soldier11.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4e08e50b', 'Soldier11.HairA.NormalMap.1024')),
    ],
    '4e08e50b': [
        (log,                           ('1.0: Soldier11 HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('2fa74e2f', 'Soldier11.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('68d9644a', 'Soldier11.HairA.NormalMap.2048')),
    ],


    '2f88092e': [(log, ('1.0 - 2.0: Soldier11 BodyA LightMap 2048p Hash',)), (update_hash, ('33e8af55',))],
    'ce581269': [(log, ('1.0 - 2.0: Soldier11 BodyA LightMap 1024p Hash',)), (update_hash, ('744e39e9',))],
    '81db8cbe': [(log, ('1.0 - 2.0: Soldier11 BodyA MaterialMap 2048p Hash',)), (update_hash, ('8ab5b59d',))],
    '874f9f68': [(log, ('1.0 - 2.0: Soldier11 BodyA MaterialMap 1024p Hash',)), (update_hash, ('9d09159b',))],


    '640a8c01': [
        (log,                           ('1.0: Soldier11 BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('e3ee72d9', 'Soldier11.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d7f2269b', 'Soldier11.BodyA.Diffuse.1024')),
    ],
    'd7f2269b': [
        (log,                           ('1.0: Soldier11 BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('e3ee72d9', 'Soldier11.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('640a8c01', 'Soldier11.BodyA.Diffuse.2048')),
    ],
    '33e8af55': [
        (log,                           ('2.0: Soldier11 BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('e3ee72d9', 'Soldier11.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('744e39e9', 'ce581269'), 'Soldier11.BodyA.LightMap.1024')),
    ],
    '744e39e9': [
        (log,                           ('2.0: Soldier11 BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('e3ee72d9', 'Soldier11.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('33e8af55', '2f88092e'), 'Soldier11.BodyA.LightMap.2048')),
    ],
    '8ab5b59d': [
        (log,                           ('2.0: Soldier11 BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('e3ee72d9', 'Soldier11.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('9d09159b', '874f9f68'), 'Soldier11.BodyA.MaterialMap.1024')),
    ],
    '9d09159b': [
        (log,                           ('2.0: Soldier11 BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('e3ee72d9', 'Soldier11.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('8ab5b59d', '81db8cbe'), 'Soldier11.BodyA.MaterialMap.2048')),
    ],
    'c94bb3d6': [
        (log,                           ('1.0: Soldier11 BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('e3ee72d9', 'Soldier11.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('eb924a91', 'Soldier11.BodyA.NormalMap.1024')),
    ],
    'eb924a91': [
        (log,                           ('1.0: Soldier11 BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('e3ee72d9', 'Soldier11.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c94bb3d6', 'Soldier11.BodyA.NormalMap.2048')),
    ],



    # MARK: Soukaku
    'fe70c7a3': [(log, ('1.0: Soukaku Hair IB Hash',)), (add_ib_check_if_missing,)],
    'ced49ff8': [(log, ('1.0: Soukaku Body IB Hash',)), (add_ib_check_if_missing,)],
    '1315178e': [(log, ('1.1: Soukaku Mask IB Hash',)), (add_ib_check_if_missing,)],
    '020f9ac6': [(log, ('1.1: Soukaku Face IB Hash',)), (add_ib_check_if_missing,)],

    '01f7369e': [(log, ('1.0 - 1.1: Soukaku Face IB Hash',)), (update_hash, ('020f9ac6',))],


    '2ceacde6': [
        (log,                           ('1.0: Soukaku FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('020f9ac6', '01f7369e'), 'Soukaku.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('427b39a4', 'Soukaku.FaceA.Diffuse.2048')),
    ],
    'c20a8c82': [
        (log,                           ('1.0: Soukaku FaceA LightMap 1024p Hash',)),
        (add_section_if_missing,        (('020f9ac6', '01f7369e'), 'Soukaku.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('17110d01', 'Soukaku.FaceA.Diffuse.2048')),
    ],
    '427b39a4': [
        (log,                           ('1.0: Soukaku FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('020f9ac6', '01f7369e'), 'Soukaku.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2ceacde6', 'Soukaku.FaceA.Diffuse.1024')),
    ],
    '17110d01': [
        (log,                           ('1.0: Soukaku FaceA LightMap 2048p Hash',)),
        (add_section_if_missing,        (('020f9ac6', '01f7369e'), 'Soukaku.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c20a8c82', 'Soukaku.FaceA.Diffuse.1024')),
    ],


    '04654e94': [(log, ('1.0 -> 2.0: Soukaku HairA LightMap 2048p Hash',)),       (update_hash, ('a70e24a2',))],
    '7bbb3d02': [(log, ('1.0 -> 2.0: Soukaku HairA LightMap 1024p Hash',)),       (update_hash, ('5966c5e3',))],


    '32ea0d00': [
        (log,                           ('1.0: Soukaku HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('fe70c7a3', 'Soukaku.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('34a3ff5b', 'Soukaku.HairA.Diffuse.1024')),
    ],
    '34a3ff5b': [
        (log,                           ('1.0: Soukaku HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('fe70c7a3', 'Soukaku.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('32ea0d00', 'Soukaku.HairA.Diffuse.2048')),
    ],
    'a70e24a2': [
        (log,                           ('2.0: Soukaku HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('fe70c7a3', 'Soukaku.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('5966c5e3', '7bbb3d02'), 'Soukaku.HairA.LightMap.1024')),
    ],
    '5966c5e3': [
        (log,                           ('2.0: Soukaku HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('fe70c7a3', 'Soukaku.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('a70e24a2', '04654e94'), 'Soukaku.HairA.LightMap.2048')),
    ],
    'd1444c52': [
        (log,                           ('1.0: Soukaku HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('fe70c7a3', 'Soukaku.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('218689cf', 'Soukaku.HairA.MaterialMap.1024')),
    ],
    '218689cf': [
        (log,                           ('1.0: Soukaku HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('fe70c7a3', 'Soukaku.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d1444c52', 'Soukaku.HairA.MaterialMap.2048')),
    ],
    '8498ee4d': [
        (log,                           ('1.0: Soukaku HairA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('fe70c7a3', 'Soukaku.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0003126a', 'Soukaku.HairA.NormalMap.1024')),
    ],
    '0003126a': [
        (log,                           ('1.0: Soukaku HairA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('fe70c7a3', 'Soukaku.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8498ee4d', 'Soukaku.HairA.NormalMap.2048')),
    ],


    'ee31954b': [
        (log,                           ('1.0: Soukaku BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('ced49ff8', 'Soukaku.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6f5d31fc', 'Soukaku.BodyA.Diffuse.1024')),
    ],
    '6f5d31fc': [
        (log,                           ('1.0: Soukaku BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('ced49ff8', 'Soukaku.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ee31954b', 'Soukaku.BodyA.Diffuse.2048')),
    ],
    '112a36a4': [
        (log,                           ('1.0: Soukaku BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('ced49ff8', 'Soukaku.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c0f0bb74', 'Soukaku.BodyA.LightMap.1024')),
    ],
    'c0f0bb74': [
        (log,                           ('1.0: Soukaku BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('ced49ff8', 'Soukaku.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('112a36a4', 'Soukaku.BodyA.LightMap.2048')),
    ],
    'd638ddf9': [
        (log,                           ('1.0: Soukaku BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('ced49ff8', 'Soukaku.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1ec28297', 'Soukaku.BodyA.MaterialMap.1024')),
    ],
    '1ec28297': [
        (log,                           ('1.0: Soukaku BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('ced49ff8', 'Soukaku.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d638ddf9', 'Soukaku.BodyA.MaterialMap.2048')),
    ],
    '363e3d70': [
        (log,                           ('1.0: Soukaku BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('ced49ff8', 'Soukaku.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('77c48d32', 'Soukaku.BodyA.NormalMap.1024')),
    ],
    '77c48d32': [
        (log,                           ('1.0: Soukaku BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('ced49ff8', 'Soukaku.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('363e3d70', 'Soukaku.BodyA.NormalMap.2048')),
    ],



    # MARK: Trigger
    '8e98ef9a': [(log, ('1.6: Trigger Hair IB Hash',)), (add_ib_check_if_missing,)],
    '7f32eeae': [(log, ('1.6: Trigger Body IB Hash',)), (add_ib_check_if_missing,)],
    '40cd4182': [(log, ('1.6: Trigger Face IB Hash',)), (add_ib_check_if_missing,)],

    # Face
    '88728785': [
        (log,                           ('1.6: Trigger FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('40cd4182', 'Trigger.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('cffc4b09', 'Trigger.FaceA.Diffuse.1024')),
    ],
    'cffc4b09': [
        (log,                           ('1.6: Trigger FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('40cd4182', 'Trigger.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('88728785', 'Trigger.FaceA.Diffuse.2048')),
    ],

    # Hair
    'e826a564': [
        (log,                           ('1.6: Trigger HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('8e98ef9a', 'Trigger.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('984e7896', 'Trigger.HairA.Diffuse.1024')),
    ],
    '984e7896': [
        (log,                           ('1.6: Trigger HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('8e98ef9a', 'Trigger.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e826a564', 'Trigger.HairA.Diffuse.2048')),
    ],
    '23f2a4cf': [
        (log,                           ('1.6: Trigger HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('8e98ef9a', 'Trigger.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c321345c', 'Trigger.HairA.LightMap.1024')),
    ],
    'c321345c': [
        (log,                           ('1.6: Trigger HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('8e98ef9a', 'Trigger.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('23f2a4cf', 'Trigger.HairA.LightMap.2048')),
    ],
    'b24f1752': [
        (log,                           ('1.6: Trigger HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('8e98ef9a', 'Trigger.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4ee3c3fe', 'Trigger.HairA.MaterialMap.1024')),
    ],
    '4ee3c3fe': [
        (log,                           ('1.6: Trigger HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('8e98ef9a', 'Trigger.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b24f1752', 'Trigger.HairA.MaterialMap.2048')),
    ],

    # Body
    '6631eadc': [
        (log,                           ('1.6: Trigger BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('7f32eeae', 'Trigger.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8cffa733', 'Trigger.BodyA.Diffuse.1024')),
    ],
    '8cffa733': [
        (log,                           ('1.6: Trigger BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('7f32eeae', 'Trigger.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6631eadc', 'Trigger.BodyA.Diffuse.2048')),
    ],
    '05250215': [
        (log,                           ('1.6: Trigger BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('7f32eeae', 'Trigger.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2c72b961', 'Trigger.BodyA.LightMap.1024')),
    ],
    '2c72b961': [
        (log,                           ('1.6: Trigger BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('7f32eeae', 'Trigger.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('05250215', 'Trigger.BodyA.LightMap.2048')),
    ],
    '985c5f52': [
        (log,                           ('1.6: Trigger BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('7f32eeae', 'Trigger.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('cd507047', 'Trigger.BodyA.MaterialMap.1024')),
    ],
    'cd507047': [
        (log,                           ('1.6: Trigger BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('7f32eeae', 'Trigger.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('985c5f52', 'Trigger.BodyA.MaterialMap.2048')),
    ],



    # MARK: Vivian
    'c4eb6168': [(log, ('1.7: Vivian Hair IB Hash',)), (add_ib_check_if_missing,)],
    'cd609d98': [(log, ('1.7: Vivian Body IB Hash',)), (add_ib_check_if_missing,)],
    '39944f20': [(log, ('1.7: Vivian Face IB Hash',)), (add_ib_check_if_missing,)],

    # Face
    '7b262ab6': [
        (log,                           ('1.7: Vivian FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('39944f20', 'Vivian.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('66b5da8e', 'Vivian.FaceA.Diffuse.1024')),
    ],
    '66b5da8e': [
        (log,                           ('1.7: Vivian FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('39944f20', 'Vivian.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7b262ab6', 'Vivian.FaceA.Diffuse.2048')),
    ],

    # Hair
    'a84d933f': [
        (log,                           ('1.7: Vivian HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('c4eb6168', 'Vivian.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2df6f7b5', 'Vivian.HairA.Diffuse.1024')),
    ],
    '2df6f7b5': [
        (log,                           ('1.7: Vivian HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('c4eb6168', 'Vivian.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a84d933f', 'Vivian.HairA.Diffuse.2048')),
    ],
    '8e3a20ea': [
        (log,                           ('1.7: Vivian HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('c4eb6168', 'Vivian.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('36b80366', 'Vivian.HairA.LightMap.1024')),
    ],
    '36b80366': [
        (log,                           ('1.7: Vivian HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('c4eb6168', 'Vivian.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('8e3a20ea', 'Vivian.HairA.LightMap.2048')),
    ],
    '2af66072': [
        (log,                           ('1.7: Vivian HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('c4eb6168', 'Vivian.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2d5b1412', 'Vivian.HairA.MaterialMap.1024')),
    ],
    '2d5b1412': [
        (log,                           ('1.7: Vivian HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('c4eb6168', 'Vivian.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2af66072', 'Vivian.HairA.MaterialMap.2048')),
    ],

    # Body
    '0635e2dd': [
        (log,                           ('1.7: Vivian BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('cd609d98', 'Vivian.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('da41fbd6', 'Vivian.BodyA.Diffuse.1024')),
    ],
    'da41fbd6': [
        (log,                           ('1.7: Vivian BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('cd609d98', 'Vivian.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('0635e2dd', 'Vivian.BodyA.Diffuse.2048')),
    ],
    'e21c3a6b': [
        (log,                           ('1.7: Vivian BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('cd609d98', 'Vivian.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4a86e169', 'Vivian.BodyA.LightMap.1024')),
    ],
    '4a86e169': [
        (log,                           ('1.7: Vivian BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('cd609d98', 'Vivian.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e21c3a6b', 'Vivian.BodyA.LightMap.2048')),
    ],
    '81f7d37c': [
        (log,                           ('1.7: Vivian BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('cd609d98', 'Vivian.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('fa650e6c', 'Vivian.BodyA.MaterialMap.1024')),
    ],
    'fa650e6c': [
        (log,                           ('1.7: Vivian BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('cd609d98', 'Vivian.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('81f7d37c', 'Vivian.BodyA.MaterialMap.2048')),
    ],



    # MARK: Wise
    'f6cac296': [(log, ('1.0: Wise Hair IB Hash',)), (add_ib_check_if_missing,)],
    'b1df5d22': [(log, ('1.0: Wise Bag IB Hash',)),  (add_ib_check_if_missing,)],
    '8d6acf4e': [(log, ('1.1: Wise Body IB Hash',)), (add_ib_check_if_missing,)],
    '1fdaf388': [(log, ('1.6: Wise Face IB Hash',)), (add_ib_check_if_missing,)],


    '054ea752': [(log, ('1.0 -> 1.1: Wise Body IB Hash',)),                 (update_hash, ('8d6acf4e',))],
    '73c48816': [(log, ('1.0 -> 1.1: Wise Body Draw Hash',)),               (update_hash, ('b581dc0a',))],
    '9581de22': [(log, ('1.0 -> 1.1: Wise Body Position Hash',)),           (update_hash, ('67f21c9f',))],
    'a012c752': [(log, ('1.0 -> 1.1: Wise Body Texcoord Hash',)),           (update_hash, ('f425bd04',))],
    '6c4ae8ce': [(log, ('1.0 -> 1.1: Wise FaceA Diffuse 1024p Hash',)),     (update_hash, ('588d7d2d',))],

    # Reversed in v1.6
    # '67f21c9f': [(log, ('1.2 -> 1.3: Wise Body Position Hash',)),         (update_hash, ('f6c5b9f3',))],
    # 'f425bd04': [(log, ('1.2 -> 1.3: Wise Body Texcoord Hash',)),         (update_hash, ('a9d5b70d',))],
    'cb22cb95': [(log, ('1.2 -> 1.3: Wise Bag Texcoord Hash',)),            (update_hash, ('2ae08ae7',))],

    'f6c5b9f3': [(log, ('1.5 -> 1.6: Wise Body Position Hash',)),           (update_hash, ('67f21c9f',))],
    'a9d5b70d': [(log, ('1.5 -> 1.6: Wise Body Texcoord Hash',)),           (update_hash, ('f425bd04',))],
    '4894246e': [(log, ('1.5 -> 1.6: Wise Face IB Hash',)),                 (update_hash, ('1fdaf388',))],

    '1d55bd87': [(log, ('1.0 -> 2.0: Wise Body Blend Hash',)),              (update_hash, ('46462bd8',))],


    '588d7d2d': [
        (log,                           ('1.1: Wise FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('1fdaf388', '4894246e'), 'Wise.Face.IB', 'match_priority = 0\n')),
    ],
    '8f9d78c1': [
        (log,                           ('1.0: Wise FaceA LightMap 1024p Hash',)),
        (add_section_if_missing,        (('1fdaf388', '4894246e'), 'Wise.Face.IB', 'match_priority = 0\n')),
    ],


    '1f21c633': [(log, ('1.0 -> 2.0: Wise HairA, BagA LightMap 2048p Hash',)),      (update_hash, ('8d8269f8',))],
    '6fcc4ad4': [(log, ('1.0 -> 2.0: Wise HairA, BagA LightMap 1024p Hash',)),      (update_hash, ('33368e12',))],
    '473f816d': [(log, ('1.0 -> 2.0: Wise HairA, BagA MaterialMap 2048p Hash',)),   (update_hash, ('f1b20f3d',))],
    '7c8b0713': [(log, ('1.0 -> 2.0: Wise HairA, BagA MaterialMap 1024p Hash',)),   (update_hash, ('d9383a15',))],


    '28005a5b': [
        (log,                           ('1.0: Wise HairA, BagA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('f6cac296', 'Wise.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('cb0d0c22', 'Wise.HairA.Diffuse.1024')),
    ],
    'cb0d0c22': [
        (log,                           ('1.0: Wise HairA, BagA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('f6cac296', 'Wise.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('28005a5b', 'Wise.HairA.Diffuse.2048')),
    ],
    '8d8269f8': [
        (log,                           ('2.0: Wise HairA, BagA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('f6cac296', 'Wise.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('33368e12', '6fcc4ad4'), 'Wise.HairA.LightMap.1024')),
    ],
    '33368e12': [
        (log,                           ('2.0: Wise HairA, BagA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('f6cac296', 'Wise.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('8d8269f8', '1f21c633'), 'Wise.HairA.LightMap.2048')),
    ],
    'f1b20f3d': [
        (log,                           ('2.0: Wise HairA, BagA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('f6cac296', 'Wise.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('d9383a15', '7c8b0713'), 'Wise.HairA.MaterialMap.1024')),
    ],
    'd9383a15': [
        (log,                           ('2.0: Wise HairA, BagA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('f6cac296', 'Wise.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('f1b20f3d', '473f816d'), 'Wise.HairA.MaterialMap.2048')),
    ],
    '3b4f22ad': [
        (log,                           ('1.0: Wise HairA, BagA NormalMap 2048p Hash',)),
        (add_section_if_missing,        ('f6cac296', 'Wise.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('db08bb73', 'Wise.HairA.NormalMap.1024')),
    ],
    'db08bb73': [
        (log,                           ('1.0: Wise HairA, BagA NormalMap 1024p Hash',)),
        (add_section_if_missing,        ('f6cac296', 'Wise.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('3b4f22ad', 'Wise.HairA.NormalMap.2048')),
    ],


    '84529dab': [(log, ('1.0 - 1.1: Wise BodyA Diffuse 2048p Hash',)), (update_hash, ('868709f2',))],
    'ef76b675': [(log, ('1.0 - 1.1: Wise BodyA Diffuse 1024p Hash',)), (update_hash, ('3d7a53b0',))],


    '868709f2': [
        (log,                           ('1.1: Wise BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('8d6acf4e', '054ea752'), 'Wise.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('3d7a53b0', 'ef76b675'), 'Wise.BodyA.Diffuse.1024')),
    ],
    '3d7a53b0': [
        (log,                           ('1.1: Wise BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('8d6acf4e', '054ea752'), 'Wise.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('868709f2', '84529dab'), 'Wise.BodyA.Diffuse.2048')),
    ],
    '088718a9': [
        (log,                           ('1.0: Wise BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        (('8d6acf4e', '054ea752'), 'Wise.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9f46182a', 'Wise.BodyA.LightMap.1024')),
    ],
    '9f46182a': [
        (log,                           ('1.0: Wise BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        (('8d6acf4e', '054ea752'), 'Wise.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('088718a9', 'Wise.BodyA.LightMap.2048')),
    ],
    'a5fdb5e7': [
        (log,                           ('1.0: Wise BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        (('8d6acf4e', '054ea752'), 'Wise.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('148283b7', 'Wise.BodyA.MaterialMap.1024')),
    ],
    '148283b7': [
        (log,                           ('1.0: Wise BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        (('8d6acf4e', '054ea752'), 'Wise.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a5fdb5e7', 'Wise.BodyA.MaterialMap.2048')),
    ],
    'f43c8025': [
        (log,                           ('1.0: Wise BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        (('8d6acf4e', '054ea752'), 'Wise.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('6807521d', 'Wise.BodyA.NormalMap.1024')),
    ],
    '6807521d': [
        (log,                           ('1.0: Wise BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        (('8d6acf4e', '054ea752'), 'Wise.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f43c8025', 'Wise.BodyA.NormalMap.2048')),
    ],



    # MARK: WiseSkin
    '6acc1eb8': [(log, ('2.0: WiseSkin Body IB Hash',)), (add_ib_check_if_missing,)],


    '81406abe': [
        (log,                           ('2.0: WiseSkin BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('6acc1eb8', 'WiseSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9fc3646e', 'WiseSkin.BodyA.Diffuse.1024')),
    ],
    '9fc3646e': [
        (log,                           ('2.0: WiseSkin BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('6acc1eb8', 'WiseSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('81406abe', 'WiseSkin.BodyA.Diffuse.2048')),
    ],
    '05b25d35': [
        (log,                           ('2.0: WiseSkin BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('6acc1eb8', 'WiseSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('dd79b44b', 'WiseSkin.BodyA.LightMap.1024')),
    ],
    'dd79b44b': [
        (log,                           ('2.0: WiseSkin BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('6acc1eb8', 'WiseSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('05b25d35', 'WiseSkin.BodyA.LightMap.2048')),
    ],
    '24af1f48': [
        (log,                           ('2.0: WiseSkin BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('6acc1eb8', 'WiseSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('aa712fb9', 'WiseSkin.BodyA.MaterialMap.1024')),
    ],
    'aa712fb9': [
        (log,                           ('2.0: WiseSkin BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('6acc1eb8', 'WiseSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('24af1f48', 'WiseSkin.BodyA.MaterialMap.2048')),
    ],



    # MARK: Yanagi
    '9e12899f': [(log, ('1.3: Yanagi Hair IB Hash',)),    (add_ib_check_if_missing,)],
    'f478ee4c': [(log, ('1.3: Yanagi Body IB Hash',)),    (add_ib_check_if_missing,)],
    # '27d49f0b': [(log, ('1.3: Yanagi Sheathe IB Hash',)), (add_ib_check_if_missing,)],
    # '2d7f2223': [(log, ('1.3: Yanagi Weapon IB Hash',)),  (add_ib_check_if_missing,)],
    '0817204c': [(log, ('1.3: Yanagi Face IB Hash',)),    (add_ib_check_if_missing,)],


    '95d9e92e': [
        (log,                           ('1.3: Yanagi FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('0817204c', 'Yanagi.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('cfe7ab46', 'Yanagi.FaceA.Diffuse.1024')),
    ],
    'cfe7ab46': [
        (log,                           ('1.3: Yanagi FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('0817204c', 'Yanagi.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('95d9e92e', 'Yanagi.FaceA.Diffuse.2048')),
    ],


    'ac5f6d76': [
        (log,                           ('1.3: Yanagi HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('9e12899f', 'Yanagi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('4edb5c79', 'Yanagi.HairA.Diffuse.1024')),
    ],
    '4edb5c79': [
        (log,                           ('1.3: Yanagi HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('9e12899f', 'Yanagi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ac5f6d76', 'Yanagi.HairA.Diffuse.2048')),
    ],
    '99cfa935': [
        (log,                           ('1.3: Yanagi HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('9e12899f', 'Yanagi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5a43d985', 'Yanagi.HairA.LightMap.1024')),
    ],
    '5a43d985': [
        (log,                           ('1.3: Yanagi HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('9e12899f', 'Yanagi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('99cfa935', 'Yanagi.HairA.LightMap.2048')),
    ],
    'f80b57f0': [
        (log,                           ('1.3: Yanagi HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('9e12899f', 'Yanagi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('486e3c42', 'Yanagi.HairA.MaterialMap.1024')),
    ],
    '486e3c42': [
        (log,                           ('1.3: Yanagi HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('9e12899f', 'Yanagi.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f80b57f0', 'Yanagi.HairA.MaterialMap.2048')),
    ],


    '08933e28': [(log, ('1.3 -> 2.0: Yanagi BodyA LightMap 2048p Hash',)),          (update_hash, ('616200aa',))],
    'f60602ec': [(log, ('1.3 -> 2.0: Yanagi BodyA LightMap 1024p Hash',)),          (update_hash, ('3ffcef9e',))],


    'c7c4f5c5': [
        (log,                           ('1.3: Yanagi BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('f478ee4c', 'Yanagi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c119dbd7', 'Yanagi.BodyA.Diffuse.1024')),
    ],
    'c119dbd7': [
        (log,                           ('1.3: Yanagi BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('f478ee4c', 'Yanagi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c7c4f5c5', 'Yanagi.BodyA.Diffuse.2048')),
    ],
    '616200aa': [
        (log,                           ('2.0: Yanagi BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('f478ee4c', 'Yanagi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('3ffcef9e', 'f60602ec'), 'Yanagi.BodyA.LightMap.1024')),
    ],
    '3ffcef9e': [
        (log,                           ('2.0: Yanagi BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('f478ee4c', 'Yanagi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('616200aa', '08933e28'), 'Yanagi.BodyA.LightMap.2048')),
    ],
    'c2ae5d2b': [
        (log,                           ('1.3: Yanagi BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('f478ee4c', 'Yanagi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('b29f0188', 'Yanagi.BodyA.MaterialMap.1024')),
    ],
    'b29f0188': [
        (log,                           ('1.3: Yanagi BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('f478ee4c', 'Yanagi.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c2ae5d2b', 'Yanagi.BodyA.MaterialMap.2048')),
    ],


    # 'aaccff06': [
    #     (log,                           ('1.3: Yanagi WeaponA, SheatheA Diffuse 1024p Hash',)),
    #     (add_section_if_missing,        ('2d7f2223', 'Yanagi.Weapon.IB', 'match_priority = 0\n')),
    #     (add_section_if_missing,        ('27d49f0b', 'Yanagi.Sheathe.IB', 'match_priority = 0\n')),
    #     # (multiply_section_if_missing,   ('a1eabb9f', 'Yanagi.WeaponA.Diffuse.2048')),
    # ],
    # '8ef68839': [
    #     (log,                           ('1.3: Yanagi WeaponA, SheatheA LightMap 1024p Hash',)),
    #     (add_section_if_missing,        ('2d7f2223', 'Yanagi.Weapon.IB', 'match_priority = 0\n')),
    #     (add_section_if_missing,        ('27d49f0b', 'Yanagi.Sheathe.IB', 'match_priority = 0\n')),
    #     # (multiply_section_if_missing,   ('a1eabb9f', 'Yanagi.WeaponA.LightMap.2048')),
    # ],
    # 'ecd8605e': [
    #     (log,                           ('1.3: Yanagi WeaponA, SheatheA MaterialMap 1024p Hash',)),
    #     (add_section_if_missing,        ('2d7f2223', 'Yanagi.Weapon.IB', 'match_priority = 0\n')),
    #     (add_section_if_missing,        ('27d49f0b', 'Yanagi.Sheathe.IB', 'match_priority = 0\n')),
    #     # (multiply_section_if_missing,   ('a1eabb9f', 'Yanagi.WeaponA.MaterialMap.2048')),
    # ],



    # MARK: YiXuan
    'ac8e9ee3': [(log, ('2.0: YiXuan Hair IB Hash',)),         (add_ib_check_if_missing,)],
    '029c1f5a': [(log, ('2.0: YiXuan Body IB Hash',)),         (add_ib_check_if_missing,)],
    '8c2fc05e': [(log, ('2.0: YiXuan Coat IB Hash',)),         (add_ib_check_if_missing,)],
    '8b067f99': [(log, ('2.0: YiXuan Face IB Hash',)),         (add_ib_check_if_missing,)],

    # Face
    '7d9ee001': [
        (log,                           ('2.0: YiXuan FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('8b067f99', 'YiXuan.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9efd1605', 'YiXuan.FaceA.Diffuse.1024')),
    ],
    '9efd1605': [
        (log,                           ('2.0: YiXuan FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('8b067f99', 'YiXuan.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7d9ee001', 'YiXuan.FaceA.Diffuse.2048')),
    ],

    # Hair
    '7e38b38b': [
        (log,                           ('2.0: YiXuan HairA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('ac8e9ee3', 'YiXuan.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('84fe943d', 'YiXuan.HairA.Diffuse.1024')),
    ],
    '84fe943d': [
        (log,                           ('2.0: YiXuan HairA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('ac8e9ee3', 'YiXuan.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7e38b38b', 'YiXuan.HairA.Diffuse.2048')),
    ],
    '086ac064': [
        (log,                           ('2.0: YiXuan HairA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('ac8e9ee3', 'YiXuan.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5574ca9f', 'YiXuan.HairA.LightMap.1024')),
    ],
    '5574ca9f': [
        (log,                           ('2.0: YiXuan HairA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('ac8e9ee3', 'YiXuan.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('086ac064', 'YiXuan.HairA.LightMap.2048')),
    ],
    '83b02982': [
        (log,                           ('2.0: YiXuan HairA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('ac8e9ee3', 'YiXuan.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('f4ac690c', 'YiXuan.HairA.MaterialMap.1024')),
    ],
    'f4ac690c': [
        (log,                           ('2.0: YiXuan HairA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('ac8e9ee3', 'YiXuan.Hair.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('83b02982', 'YiXuan.HairA.MaterialMap.2048')),
    ],

    # Body
    '2a4f37a6': [
        (log,                           ('2.0: YiXuan BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('029c1f5a', 'YiXuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d7db2bc6', 'YiXuan.BodyA.Diffuse.1024')),
    ],
    'd7db2bc6': [
        (log,                           ('2.0: YiXuan BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('029c1f5a', 'YiXuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2a4f37a6', 'YiXuan.BodyA.Diffuse.2048')),
    ],
    '5a291e85': [
        (log,                           ('2.0: YiXuan BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('029c1f5a', 'YiXuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('96f754a7', 'YiXuan.BodyA.LightMap.1024')),
    ],
    '96f754a7': [
        (log,                           ('2.0: YiXuan BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('029c1f5a', 'YiXuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5a291e85', 'YiXuan.BodyA.LightMap.2048')),
    ],
    'd28370ec': [
        (log,                           ('2.0: YiXuan BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('029c1f5a', 'YiXuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('aa1056a5', 'YiXuan.BodyA.MaterialMap.1024')),
    ],
    'aa1056a5': [
        (log,                           ('2.0: YiXuan BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('029c1f5a', 'YiXuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('d28370ec', 'YiXuan.BodyA.MaterialMap.2048')),
    ],

    # Coat
    'e6dca725': [
        (log,                           ('2.0: YiXuan CoatA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('8c2fc05e', 'YiXuan.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('1fcedcc3', 'YiXuan.CoatA.Diffuse.1024')),
    ],
    '1fcedcc3': [
        (log,                           ('2.0: YiXuan CoatA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('8c2fc05e', 'YiXuan.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('e6dca725', 'YiXuan.CoatA.Diffuse.2048')),
    ],
    '59b2daf9': [
        (log,                           ('2.0: YiXuan CoatA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('8c2fc05e', 'YiXuan.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c4d167c3', 'YiXuan.CoatA.LightMap.1024')),
    ],
    'c4d167c3': [
        (log,                           ('2.0: YiXuan CoatA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('8c2fc05e', 'YiXuan.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('59b2daf9', 'YiXuan.CoatA.LightMap.2048')),
    ],
    'bb581f1e': [
        (log,                           ('2.0: YiXuan CoatA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('8c2fc05e', 'YiXuan.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('fd56fa4b', 'YiXuan.CoatA.MaterialMap.1024')),
    ],
    'fd56fa4b': [
        (log,                           ('2.0: YiXuan CoatA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('8c2fc05e', 'YiXuan.Coat.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('bb581f1e', 'YiXuan.CoatA.MaterialMap.2048')),
    ],



    # MARK: YiXuanSkin
    '95de0d39': [(log, ('2.0: YiXuanSkin Body IB Hash',)),         (add_ib_check_if_missing,)],


    'fe2cc6f3': [
        (log,                           ('2.0: YiXuanSkin BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('5460dbe4', 'YiXuanSkin.BodyA.Diffuse.1024')),
    ],
    '5460dbe4': [
        (log,                           ('2.0: YiXuanSkin BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('fe2cc6f3', 'YiXuanSkin.BodyA.Diffuse.2048')),
    ],
    '867e3b95': [
        (log,                           ('2.0: YiXuanSkin BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('7369431b', 'YiXuanSkin.BodyA.LightMap.1024')),
    ],
    '7369431b': [
        (log,                           ('2.0: YiXuanSkin BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('867e3b95', 'YiXuanSkin.BodyA.LightMap.2048')),
    ],
    'c72a2356': [
        (log,                           ('2.0: YiXuanSkin BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('2d535255', 'YiXuanSkin.BodyA.MaterialMap.1024')),
    ],
    '2d535255': [
        (log,                           ('2.0: YiXuanSkin BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c72a2356', 'YiXuanSkin.BodyA.MaterialMap.2048')),
    ],


    '487db3e0': [
        (log,                           ('2.0: YiXuanSkin BodyB Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('c13cac2c', 'YiXuanSkin.BodyB.Diffuse.1024')),
    ],
    'c13cac2c': [
        (log,                           ('2.0: YiXuanSkin BodyB Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('487db3e0', 'YiXuanSkin.BodyB.Diffuse.2048')),
    ],
    'a22695c9': [
        (log,                           ('2.0: YiXuanSkin BodyB LightMap 2048p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('ed7abe1d', 'YiXuanSkin.BodyB.LightMap.1024')),
    ],
    'ed7abe1d': [
        (log,                           ('2.0: YiXuanSkin BodyB LightMap 1024p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a22695c9', 'YiXuanSkin.BodyB.LightMap.2048')),
    ],
    '16a1fb10': [
        (log,                           ('2.0: YiXuanSkin BodyB MaterialMap 2048p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('9a79cf64', 'YiXuanSkin.BodyB.MaterialMap.1024')),
    ],
    '9a79cf64': [
        (log,                           ('2.0: YiXuanSkin BodyB MaterialMap 1024p Hash',)),
        (add_section_if_missing,        ('95de0d39', 'YiXuanSkin.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('16a1fb10', 'YiXuanSkin.BodyB.MaterialMap.2048')),
    ],



    # MARK: ZhuYuan
    '6619364f': [(log, ('1.1: ZhuYuan Body IB Hash',)),         (add_ib_check_if_missing,)],
    '9821017e': [(log, ('1.0: ZhuYuan Hair IB Hash',)),         (add_ib_check_if_missing,)],
    'fcac8411': [(log, ('1.0: ZhuYuan Extras IB Hash',)),       (add_ib_check_if_missing,)],
    '5e717358': [(log, ('1.0: ZhuYuan ShoulderAmmo IB Hash',)), (add_ib_check_if_missing,)],
    'a63028ae': [(log, ('1.0: ZhuYuan HipAmmo IB Hash',)),      (add_ib_check_if_missing,)],
    'f1c241b7': [(log, ('1.0: ZhuYuan Face IB Hash',)),         (add_ib_check_if_missing,)],
    
    'a4aeb1d5': [(log, ('1.0 -> 1.1: ZhuYuan Body IB Hash',)),  (update_hash, ('6619364f',))],


    'f3569f8d': [(log, ('1.0 -> 1.1: ZhuYuan Body Position Hash',)), (update_hash, ('f595d24d',))],
    '160872c0': [(log, ('1.0 -> 1.1: ZhuYuan Body Texcoord Hash',)), (update_hash, ('cb885260',))],


    # Reverted in 1.2
    # Comment out to prevent infinite loop :/
    # 'f3c092c5': [
    #     (log, ('1.0 -> 1.1: ZhuYuan Hair Texcoord Hash',)),
    #     (update_hash, ('fdc045fc',)),
    #     (log, ('+ Remapping texcoord buffer from stride 20 to 32',)),
    #     (update_buffer_element_width, (('BBBB', 'ee', 'ff', 'ee'), ('ffff', 'ee', 'ff', 'ee'), '1.1')),
    #     (log, ('+ Setting texcoord vcolor alpha to 1',)),
    #     (update_buffer_element_value, (('ffff', 'ee', 'ff', 'ee'), ('xxx1', 'xx', 'xx', 'xx'), '1.1'))
    # ],

    'fdc045fc': [
        (log, ('1.1 -> 1.2: ZhuYuan Hair Texcoord Hash',)),
        (update_hash, ('f3c092c5',)),
        (log, ('+ Reverting texcoord buffer remap',)),
        (zzz_12_shrink_texcoord_color, ('1.2',))
    ],

    '138c7d76': [
        (log,                           ('1.0: ZhuYuan FaceA Diffuse 1024p Hash',)),
        (add_section_if_missing,        ('f1c241b7', 'ZhuYuan.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('a1eabb9f', 'ZhuYuan.FaceA.Diffuse.2048')),
    ],
    'a1eabb9f': [
        (log,                           ('1.0: ZhuYuan FaceA Diffuse 2048p Hash',)),
        (add_section_if_missing,        ('f1c241b7', 'ZhuYuan.Face.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   ('138c7d76', 'ZhuYuan.FaceA.Diffuse.1024')),
    ],


    '9b86c2f6': [
        (log,                           ('1.0: ZhuYuan HairA, ExtrasA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   ('7f823598', 'ZhuYuan.HairA.Diffuse.2048')),
    ],
    '6eb346b9': [
        (log,                           ('1.0: ZhuYuan HairA, ExtrasA NormalMap 1024p Hash',)),
        (multiply_section_if_missing,   ('4ac1defe', 'ZhuYuan.HairA.NormalMap.2048')),
    ],
    '8955095f': [
        (log,                           ('1.0: ZhuYuan HairA, ExtrasA LightMap 1024p Hash',)),
        (multiply_section_if_missing,   ('d4ee59c7', 'ZhuYuan.HairA.LightMap.2048')),
    ],
    '7d884663': [
        (log,                           ('1.0: ZhuYuan HairA, ExtrasA MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   ('12a407b1', 'ZhuYuan.HairA.MaterialMap.2048')),
    ],

    '7f823598': [
        (log,                           ('1.0: ZhuYuan HairA, ExtrasA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   ('9b86c2f6', 'ZhuYuan.HairA.Diffuse.1024')),
    ],
    '4ac1defe': [
        (log,                           ('1.0: ZhuYuan HairA, ExtrasA NormalMap 2048p Hash',)),
        (multiply_section_if_missing,   ('6eb346b9', 'ZhuYuan.HairA.NormalMap.1024')),
    ],
    'd4ee59c7': [
        (log,                           ('1.0: ZhuYuan HairA, ExtrasA LightMap 2048p Hash',)),
        (multiply_section_if_missing,   ('8955095f', 'ZhuYuan.HairA.LightMap.1024')),
    ],
    '12a407b1': [
        (log,                           ('1.0: ZhuYuan HairA, ExtrasA MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   ('7d884663', 'ZhuYuan.HairA.MaterialMap.1024')),
    ],


    'b57a8744': [(log, ('1.0 -> 1.1: ZhuYuan BodyA Diffuse 1024p Hash',)),     (update_hash, ('f6795718',))],
    '833bafd5': [(log, ('1.0 -> 1.1: ZhuYuan BodyA NormalMap 1024p Hash',)),   (update_hash, ('729ea75a',))],
    '18d00ac6': [(log, ('1.0 -> 1.1: ZhuYuan BodyA LightMap 1024p Hash',)),    (update_hash, ('14b638b6',))],
    '1daa379f': [(log, ('1.0 -> 1.1: ZhuYuan BodyA MaterialMap 1024p Hash',)), (update_hash, ('cd4dee2c',))],

    'f6795718': [(log, ('1.1 -> 1.2: ZhuYuan BodyA Diffuse 1024p Hash',)),     (update_hash, ('46af14f8',))],
    '729ea75a': [(log, ('1.1 -> 1.2: ZhuYuan BodyA NormalMap 1024p Hash',)),   (update_hash, ('d5b175bf',))],
    '14b638b6': [(log, ('1.1 -> 1.2: ZhuYuan BodyA LightMap 1024p Hash',)),    (update_hash, ('fb385169',))],
    'cd4dee2c': [(log, ('1.1 -> 1.2: ZhuYuan BodyA MaterialMap 1024p Hash',)), (update_hash, ('29e2ebc5',))],

    '46af14f8': [
        (log,                           ('1.2: ZhuYuan BodyA Diffuse 1024p Hash',)),
        (add_section_if_missing,        (('6619364f', 'a4aeb1d5'), 'ZhuYuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('a271e894', '3ef82f41', 'c88e7660'), 'ZhuYuan.BodyA.Diffuse.2048')),
    ],
    'd5b175bf': [
        (log,                           ('1.2: ZhuYuan BodyA NormalMap 1024p Hash',)),
        (add_section_if_missing,        (('6619364f', 'a4aeb1d5'), 'ZhuYuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('d81fb56e', '7195a311', 'a396c53a'), 'ZhuYuan.BodyA.NormalMap.2048')),
    ],
    'fb385169': [
        (log,                           ('1.2: ZhuYuan BodyA LightMap 1024p Hash',)),
        (add_section_if_missing,        (('6619364f', 'a4aeb1d5'), 'ZhuYuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('d02bc66c', '80ebf536', '13a38449'), 'ZhuYuan.BodyA.LightMap.2048')),
    ],
    '29e2ebc5': [
        (log,                           ('1.2: ZhuYuan BodyA MaterialMap 1024p Hash',)),
        (add_section_if_missing,        (('6619364f', 'a4aeb1d5'), 'ZhuYuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('3e808ef6', '10415de8', 'b4e20235'), 'ZhuYuan.BodyA.MaterialMap.2048')),
    ],

    'c88e7660': [(log, ('1.0 -> 1.1: ZhuYuan BodyA Diffuse 2048p Hash',)),     (update_hash, ('3ef82f41',))],
    'a396c53a': [(log, ('1.0 -> 1.1: ZhuYuan BodyA NormalMap 2048p Hash',)),   (update_hash, ('7195a311',))],
    '13a38449': [(log, ('1.0 -> 1.1: ZhuYuan BodyA LightMap 2048p Hash',)),    (update_hash, ('80ebf536',))],
    'b4e20235': [(log, ('1.0 -> 1.1: ZhuYuan BodyA MaterialMap 2048p Hash',)), (update_hash, ('10415de8',))],

    '3ef82f41': [(log, ('1.1 -> 1.2: ZhuYuan BodyA Diffuse 2048p Hash',)),     (update_hash, ('a271e894',))],
    '7195a311': [(log, ('1.1 -> 1.2: ZhuYuan BodyA NormalMap 2048p Hash',)),   (update_hash, ('d81fb56e',))],
    '80ebf536': [(log, ('1.1 -> 1.2: ZhuYuan BodyA LightMap 2048p Hash',)),    (update_hash, ('d02bc66c',))],
    '10415de8': [(log, ('1.1 -> 1.2: ZhuYuan BodyA MaterialMap 2048p Hash',)), (update_hash, ('3e808ef6',))],

    'a271e894': [
        (log,                           ('1.2: ZhuYuan BodyA Diffuse 2048p Hash',)),
        (add_section_if_missing,        (('6619364f', 'a4aeb1d5'), 'ZhuYuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('46af14f8', 'f6795718', 'b57a8744'), 'ZhuYuan.BodyA.Diffuse.1024')),
    ],
    'd81fb56e': [
        (log,                           ('1.2: ZhuYuan BodyA NormalMap 2048p Hash',)),
        (add_section_if_missing,        (('6619364f', 'a4aeb1d5'), 'ZhuYuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('d5b175bf', '729ea75a', '833bafd5'), 'ZhuYuan.BodyA.NormalMap.1024')),
    ],
    'd02bc66c': [
        (log,                           ('1.2: ZhuYuan BodyA LightMap 2048p Hash',)),
        (add_section_if_missing,        (('6619364f', 'a4aeb1d5'), 'ZhuYuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('fb385169', '14b638b6', '18d00ac6'), 'ZhuYuan.BodyA.LightMap.1024')),
    ],
    '3e808ef6': [
        (log,                           ('1.2: ZhuYuan BodyA MaterialMap 2048p Hash',)),
        (add_section_if_missing,        (('6619364f', 'a4aeb1d5'), 'ZhuYuan.Body.IB', 'match_priority = 0\n')),
        (multiply_section_if_missing,   (('29e2ebc5', 'cd4dee2c', '1daa379f'), 'ZhuYuan.BodyA.MaterialMap.1024')),
    ],


    '222ae5ee': [
        (log,                           ('1.0: ZhuYuan ExtrasB, ShoulderAmmoA, HipAmmoA Diffuse 1024p Hash',)),
        (multiply_section_if_missing,   ('6a33b25e', 'ZhuYuan.ExtrasB.Diffuse.2048')),
    ],
    '0fda74c3': [
        (log,                           ('1.0: ZhuYuan ExtrasB, ShoulderAmmoA, HipAmmoA NormalMap 1024p Hash',)),
        (multiply_section_if_missing,   ('fb35b7e9', 'ZhuYuan.ExtrasB.NormalMap.2048')),
    ],
    '790183b4': [
        (log,                           ('1.0: ZhuYuan ExtrasB, ShoulderAmmoA, HipAmmoA LightMap 1024p Hash',)),
        (multiply_section_if_missing,   ('e30f025b', 'ZhuYuan.ExtrasB.LightMap.2048')),
    ],
    '84842409': [
        (log,                           ('1.0: ZhuYuan ExtrasB, ShoulderAmmoA, HipAmmoA MaterialMap 1024p Hash',)),
        (multiply_section_if_missing,   ('58d5c840', 'ZhuYuan.ExtrasB.MaterialMap.2048')),
    ],

    '6a33b25e': [
        (log,                           ('1.0: ZhuYuan ExtrasB, ShoulderAmmoA, HipAmmoA Diffuse 2048p Hash',)),
        (multiply_section_if_missing,   ('222ae5ee', 'ZhuYuan.ExtrasB.Diffuse.1024')),
    ],
    'fb35b7e9': [
        (log,                           ('1.0: ZhuYuan ExtrasB, ShoulderAmmoA, HipAmmoA NormalMap 2048p Hash',)),
        (multiply_section_if_missing,   ('0fda74c3', 'ZhuYuan.ExtrasB.NormalMap.1024')),
    ],
    'e30f025b': [
        (log,                           ('1.0: ZhuYuan ExtrasB, ShoulderAmmoA, HipAmmoA LightMap 2048p Hash',)),
        (multiply_section_if_missing,   ('790183b4', 'ZhuYuan.ExtrasB.LightMap.1024')),
    ],
    '58d5c840': [
        (log,                           ('1.0: ZhuYuan ExtrasB, ShoulderAmmoA, HipAmmoA MaterialMap 2048p Hash',)),
        (multiply_section_if_missing,   ('84842409', 'ZhuYuan.ExtrasB.MaterialMap.1024')),
    ],



}


# MARK: Regex
# Using VERBOSE flag to ignore whitespace
# https://docs.python.org/3/library/re.html#re.VERBOSE
def get_section_hash_pattern(hash) -> re.Pattern:
    return re.compile(
        r'''
            ^(
                [ \t]*?\[(?:Texture|Shader)Override.*\][ \t]*
                (?:\n
                    (?![ \t]*?(?:\[|hash\s*=))
                    .*$
                )*?
                (?:\n\s*hash\s*=\s*{}[ \t]*)
                (?:
                    (?:\n(?![ \t]*?\[).*$)*
                    (?:\n[\t ]*?[\$\w].*$)
                )?
            )\s*
        '''.format(hash),
        flags=re.VERBOSE|re.IGNORECASE|re.MULTILINE
    )


def get_section_title_pattern(title) -> re.Pattern:
    return re.compile(
        r'''
            ^(
                [ \t]*?\[{}\]
                (?:
                    (?:\n(?![ \t]*?\[).*$)*
                    (?:\n[\t ]*?[\$\w].*$)
                )?
            )\s*
        '''.format(title),
        flags=re.VERBOSE|re.IGNORECASE|re.MULTILINE
    )



# MARK: RUN
if __name__ == '__main__':
    try: main()
    except Exception as x:
        print('\nError Occurred: {}\n'.format(x))
        print(traceback.format_exc())
    finally:
        input('\nPress "Enter" to quit...\n')
