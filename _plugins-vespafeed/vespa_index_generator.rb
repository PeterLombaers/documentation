# Copyright Yahoo. Licensed under the terms of the Apache 2.0 license. See LICENSE in the project root.

require 'json'
require 'nokogiri'
require 'kramdown/parser/kramdown'

module Jekyll

    class VespaIndexGenerator < Jekyll::Generator
        priority :lowest

        def generate(site)
            namespace = site.config["search"]["namespace"]
            operations = []
            site.pages.each do |page|
                next if page.path.start_with?("css/")
                if page.data["index"] == true &&
                        page.url.start_with?("/redirects.json") == false &&
                        !is_empty(page)
                    text = extract_text(page)
                    operations.push({
                        :put => "id:"+namespace+":doc::"+namespace+page.url,
                        :fields => {
                            :path => page.url,
                            :namespace => namespace,
                            :title => page.data["title"],
                            :content => text,
                            :term_count => text.split.length(),
                            :last_updated => Time.now.to_i,
                            :outlinks => extract_links(page)
                        }
                    })
                end
            end

            json = JSON.pretty_generate(operations)
            File.open(namespace + "_index.json", "w") { |f| f.write(json) }
        end

        def is_empty(page)
            # The generate client-side redirects should not be indexed -
            # they have no title and node content
            return page.content == "" && !page.data["title"]
        end

        def extract_text(page)
            ext = page.name[page.name.rindex('.')+1..-1]
            if ext == "md"
                input = Kramdown::Document.new(page.content).to_html
            else
                input = page.content
            end
            doc = Nokogiri::HTML(input)
            doc.search('th,td').each{ |e| e.after "\n" }
            doc.search('style').each{ |e| e.remove }
            content = doc.xpath("//text()").to_s
            page_text = content.gsub("\r"," ").gsub("\n"," ")
        end

        def extract_links(page)
            doc = Nokogiri::HTML(page.content)
            links = doc.css('a').map { |link| link['href'] || ""}
            links.map!(&:strip).reject!{|s| s.empty?}
        end

    end

end
