#!/bin/bash


# Run availables tests
pants test ::

pants fmt ::

pants lint ::

# Package Docker
pants package ::
