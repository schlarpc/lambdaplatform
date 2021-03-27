{ pkgs ? (import <nixpkgs> { }) }:
let

  extraPythonPackages = ps:
    with ps; rec {
      awacs = (buildPythonPackage rec {
        pname = "awacs";
        version = "1.0.4";
        src = fetchPypi {
          inherit pname version;
          sha256 =
            "ed17fb00b5c6e571af67c7e301862d2da8a9b8e389270e4911cb7daf373ea71a";
        };
        postInstall = ''
          rm -rf $out/${python.sitePackages}/tests
        '';
      });

      troposphere = (buildPythonPackage rec {
        pname = "troposphere";
        version = "2.7.0";
        src = fetchPypi {
          inherit pname version;
          sha256 =
            "b0ab144b989e1e1c4698e601008bd5f7fbabd0629b4588cb57d3583f8aa6edc9";
        };
        propagatedBuildInputs = [ cfn-flip awacs ];
        doCheck = false; # no tests in pypi sdist
      });

      lambdaplatform = (buildPythonPackage rec {
        pname = "lambdaplatform";
        version = "dev";
        src = pkgs.nix-gitignore.gitignoreSource [ ] ./.;
        propagatedBuildInputs = [ awacs boto3 troposphere ];
      });
    };

  interpreter = pkgs.python3.withPackages
    (ps: pkgs.lib.attrValues (extraPythonPackages ps));

  image = pkgs.dockerTools.streamLayeredImage {
    name = "lambda-image";
    contents = [ ];
    maxLayers = 20; # bug in lambda for now
    config = {
      Entrypoint = [ "${interpreter}/bin/lambdaplatform-runtime" ];
      WorkingDir = "/";
      Env = [
        "NIX_SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
        "PYTHONUNBUFFERED=1"
      ];
    };
  };

  templates = pkgs.runCommand "cloudformation-templates" { } ''
    ${interpreter}/bin/lambdaplatform-generate-templates --output-dir $out
  '';

  deploy = pkgs.writeShellScript "deploy" ''
    export PATH=${pkgs.skopeo}/bin:$PATH
    export LAMBDAPLATFORM_TEMPLATE_PATH=${templates}
    export LAMBDAPLATFORM_PRIMARY_TEMPLATE_PATH=${templates}/primary.json
    export LAMBDAPLATFORM_IMAGE_GENERATOR=${image}
    exec ${interpreter}/bin/lambdaplatform-deploy $@
  '';

  linkFarm =
    pkgs.linkFarmFromDrvs "lambdaplatform-link-farm" [ image templates deploy ];

in linkFarm
