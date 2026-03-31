# Homebrew formula for TerraForge — AI-Powered Coder Workspace Template Generator
# Tap:  brew tap s6labs/terraforge
# Install: brew install s6labs/terraforge/terraforge
#
# To update checksums after a new release, run:
#   brew bump-formula-pr --tag vX.Y.Z --revision <commit-sha> terraforge
#
class Terraforge < Formula
  desc "AI-Powered Coder Workspace Template Generator"
  homepage "https://github.com/s6labs/terraforge"
  license "MIT"
  version "1.5.0"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/s6labs/terraforge/releases/download/v#{version}/terraforge-macos-arm64.tar.gz"
      sha256 "REPLACE_WITH_SHA256_MACOS_ARM64"

      def install
        bin.install "terraforge-macos-arm64" => "terraforge"
      end
    else
      url "https://github.com/s6labs/terraforge/releases/download/v#{version}/terraforge-macos-intel.tar.gz"
      sha256 "REPLACE_WITH_SHA256_MACOS_INTEL"

      def install
        bin.install "terraforge-macos-intel" => "terraforge"
      end
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://github.com/s6labs/terraforge/releases/download/v#{version}/terraforge-linux-arm64.tar.gz"
      sha256 "REPLACE_WITH_SHA256_LINUX_ARM64"

      def install
        bin.install "terraforge-linux-arm64" => "terraforge"
      end
    else
      url "https://github.com/s6labs/terraforge/releases/download/v#{version}/terraforge-linux-amd64.tar.gz"
      sha256 "REPLACE_WITH_SHA256_LINUX_AMD64"

      def install
        bin.install "terraforge-linux-amd64" => "terraforge"
      end
    end
  end

  test do
    assert_match "terraforge", shell_output("#{bin}/terraforge --help 2>&1", 0)
  end
end
