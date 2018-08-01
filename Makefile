# documentation:
documentation:
	doxygen doxy_config
	if [ ! -d "doc/html/images" ]; then ln -s ../../images doc/html/images; fi
markdown:
	if [ -e "README.html" ]; then rm README.html; fi
	markdown README.md >> README.html
