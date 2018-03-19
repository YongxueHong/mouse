#!/usr/bin/env bash
yum_utils_list=(
pexpect
python-paramiko
nc
bridge-utils
)

pip_utils_list=(
pyyaml
progressbar
tqdm
)

for utils in ${yum_utils_list[@]}
do
    echo -e "\n==========>>>>>>>>>Installing package $utils "
    echo -e "**************************************************************************"
    yum install -y $utils
    wait
    echo -e "**************************************************************************"
done

for utils in ${yum_utils_list[@]}
do
    echo -e "\n==========>>>>>>>>>Checking package $utils "
    echo -e "**************************************************************************"
    yum list installed | grep $utils
    wait
    echo -e "**************************************************************************"
done

for utils in ${pip_utils_list[@]}
do
    echo -e "\n==========>>>>>>>>>Installing package $utils "
    echo -e "**************************************************************************"
    pip install $utils
    wait
    echo -e "**************************************************************************"
done

for utils in ${pip_utils_list[@]}
do
    echo -e "\n==========>>>>>>>>>Checking package $utils "
    echo -e "**************************************************************************"
    pip show $utils
    wait
    echo -e "**************************************************************************"
done