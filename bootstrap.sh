#!/usr/bin/env bash
yum_utils_list=(
nc
bridge-utils
)

pip_utils_list=(
pyyaml
pexpect
paramiko==2.1.1
progressbar
tqdm
)

easy_install_update_utils_list=(
pexpect
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

for utils in ${easy_install_update_utils_list[@]}
do
echo -e "\n==========>>>>>>>>>update package "
easy_install --upgrade $utils
echo -e "**************************************************************************"
done

if [ $1 ]
then
  ssh root@$1 ntpdate clock.redhat.com
  echo "update the clock of $1"
fi

ntpdate clock.redhat.com
echo "update the clock of local host"