#!/usr/bin/env python3
"""Restrict forwarded workload-metadata access to the designated Sheets container."""
import argparse
import ipaddress
import json
import os
import subprocess

CHAIN = 'DAWEI-METADATA'


def apply(sheets_ip):
    ip = ipaddress.ip_address(sheets_ip)
    if ip.version != 4 or not ip.is_private:
        raise ValueError('Require the private static IPv4 address of the Sheets container')
    if os.geteuid() != 0:
        raise ValueError('Root is required for metadata isolation')
    rulesets = {
        'iptables': [
            ['-s', str(ip) + '/32', '-d', '169.254.169.254/32', '-j', 'RETURN'],
            ['-d', '169.254.169.254/32', '-j', 'REJECT', '--reject-with', 'icmp-port-unreachable']],
        'ip6tables': [
            ['-d', 'fd20:ce::254/128', '-j', 'REJECT', '--reject-with', 'icmp6-port-unreachable']]}
    def command(binary, *args, check=True):
        return subprocess.run([binary, '-w', '10', *args], check=check, capture_output=True, text=True, timeout=20)
    for binary, rules in rulesets.items():
        command(binary, '-S', 'DOCKER-USER')
        command(binary, '-N', CHAIN, check=False)
        existing = command(binary, '-S', CHAIN).stdout.splitlines()
        entries = [line for line in existing if line.startswith('-A ')]
        present = [command(binary, '-C', CHAIN, *rule, check=False).returncode == 0 for rule in rules]
        if len(entries) != sum(present):
            raise ValueError('Unexpected existing metadata-isolation rules; refusing to replace them')
        for rule, exists in zip(rules, present):
            if not exists:
                command(binary, '-A', CHAIN, *rule)
        hook = '-A DOCKER-USER -j ' + CHAIN
        docker = command(binary, '-S', 'DOCKER-USER').stdout.splitlines()
        jumps = [line for line in docker if line == hook]
        if not jumps:
            command(binary, '-I', 'DOCKER-USER', '1', '-j', CHAIN)
        docker = [line for line in command(binary, '-S', 'DOCKER-USER').stdout.splitlines() if line.startswith('-A ')]
        if not docker or docker[0] != hook or docker.count(hook) != 1:
            raise ValueError('Metadata-isolation hook is not the first unique Docker rule')
        forwarding = [line for line in command(binary, '-S', 'FORWARD').stdout.splitlines() if line.startswith('-A ')]
        if not forwarding or forwarding[0] != '-A FORWARD -j DOCKER-USER':
            raise ValueError('Docker user rules are not first in forwarding; verify host firewall ordering')
    return {'status': 'CONFIGURED', 'ipv4_metadata': 'DESIGNATED_SHEETS_ONLY',
            'ipv6_metadata': 'FORWARDED_ACCESS_DENIED', 'existing_firewall_flushed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sheets-ip', default='172.29.0.6')
    args = parser.parse_args()
    print(json.dumps(apply(args.sheets_ip)))
